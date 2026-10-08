"""Open Boxing integration: a bundled MIT-licensed historical archive plus optional weekly updates.

Upstream: https://github.com/edhwright/open-boxing
CSV: src/db/data/bouts.csv, src/db/data/champions.csv
This archive is *not* a source of up-to-date fight schedules or complete career records.
"""
import json
import re
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import requests

SOURCE = "https://openboxing.org/api/bouts/all.json"
SEED = Path(__file__).resolve().parent / "data" / "openboxing_archive.json"
LICENSE = "https://github.com/edhwright/open-boxing/blob/main/LICENSE.md"


def _text(value):
    return str(value).strip() if value is not None else ""


def _identifier(champion_id, name):
    if str(champion_id or "").strip().isdigit():
        return "ob-c-" + str(int(champion_id))
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")
    return ("ob-name-" + slug)[:95]


def _integer(value):
    try:
        return int(value) if str(value).strip() else None
    except (ValueError, TypeError):
        return None


def _save_rows(champions, bouts):
    """Insert one SQLite transaction; leave existing Fightbase data untouched."""
    from boxing_feed import connect, utcnow
    added = 0
    with connect() as conn:
        for row in champions:
            if len(row) < 2 or not row[1]:
                continue
            cid = _identifier(row[0], row[1])
            conn.execute("""INSERT INTO hub_fighters(id,name,updated_at)
                VALUES (?,?,?) ON CONFLICT(id) DO NOTHING""",
                (cid, _text(row[1]), utcnow()))
        for row in bouts:
            if len(row) < 11:
                continue
            bout_id, fought_on, aid, aname, bid, bname, winner, method, ended, scheduled, weight = row[:11]
            if not _text(aname) or not _text(bname):
                continue
            try:
                when = date.fromisoformat(str(fought_on)[:10])
            except ValueError:
                continue
            # Never render upstream stale "SCHEDULED" records as upcoming results.
            if when > date.today():
                continue
            a_id = _identifier(aid, aname)
            b_id = _identifier(bid, bname)
            for fid, name in ((a_id, aname), (b_id, bname)):
                conn.execute("""INSERT INTO hub_fighters(id,name,updated_at)
                    VALUES (?,?,?) ON CONFLICT(id) DO NOTHING""",
                    (fid, _text(name), utcnow()))
            who = _text(winner).upper()
            winner_id = a_id if who == "BOXER A" else b_id if who == "BOXER B" else ""
            mid = "ob-" + str(bout_id)
            cursor = conn.execute("""INSERT INTO hub_fights
                (id,fight_date,title,status,a_id,b_id,a_name,b_name,winner_id,
                 outcome,result_round,division,event_id,event_title,rounds,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO NOTHING""",
                (mid,str(when),_text(aname)+" vs "+_text(bname),"FINISHED",
                 a_id,b_id,_text(aname),_text(bname),winner_id,_text(method),
                 _text(ended),_text(weight),"","Open Boxing (historisches Archiv)",
                 _integer(scheduled),utcnow()))
            added += max(0,cursor.rowcount)
    return added


def load_bundled_archive():
    """Populate Fightbase even without access to the internet."""
    from boxing_feed import connect
    if not SEED.is_file():
        return 0
    with connect() as c:
        row = c.execute("SELECT value FROM hub_meta WHERE key='openboxing_seed_version'").fetchone()
    if row and row["value"] == "1":
        return 0
    payload = json.loads(SEED.read_text(encoding="utf-8"))
    added = _save_rows(payload.get("champions", []), payload.get("bouts", []))
    with connect() as c:
        c.execute("""INSERT INTO hub_meta(key,value) VALUES ('openboxing_seed_version','1')
        ON CONFLICT(key) DO UPDATE SET value='1'""")
    return added


def refresh_remote_archive():
    """Optional, at most weekly. A failed network call never empties the local archive."""
    from boxing_feed import connect, utcnow
    with connect() as c:
        saved = c.execute("SELECT value FROM hub_meta WHERE key='openboxing_remote_checked'").fetchone()
    if saved:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(saved["value"]) < timedelta(days=7):
                return 0
        except ValueError:
            pass
    response = requests.get(SOURCE, timeout=25,
        headers={"Accept":"application/json",
                 "User-Agent":"FightbaseAcademicProject/1.0 (historical public boxing data)"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Unexpected Open Boxing response")
    normalized = []
    for item in payload:
        if not isinstance(item, dict) or item.get("status") != "FINISHED":
            continue
        a = (item.get("boxers") or {}).get("boxerA") or {}
        b = (item.get("boxers") or {}).get("boxerB") or {}
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        def name(boxer):
            raw = boxer.get("name")
            if isinstance(raw, dict):
                return " ".join(_text(raw.get(part)) for part in ("first","last")).strip()
            if isinstance(raw, str):
                return raw.strip()
            return _text(boxer.get("fullName"))
        result = item.get("result")
        result = result if isinstance(result,dict) else {}
        weight = item.get("weight")
        weight = weight if isinstance(weight,dict) else {}
        a_name, b_name = name(a), name(b)
        if not a_name or not b_name:
            continue
        normalized.append([
            item.get("boutId"), item.get("date"),
            a.get("championId"), a_name, b.get("championId"), b_name,
            result.get("winner"), result.get("methodOfVictory"),
            result.get("totalRounds"), item.get("scheduledRounds"), weight.get("class")
        ])
    added = _save_rows([], normalized)
    with connect() as c:
        c.execute("""INSERT INTO hub_meta(key,value) VALUES('openboxing_remote_checked',?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (utcnow(),))
    return added
