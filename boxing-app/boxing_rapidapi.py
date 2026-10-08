"""Optional Boxing Data API (RapidAPI) integration for Fightbase.

Free Basic: 100 provider requests/month advertised. This integration caps
itself at 30 attempts/month in local SQLite, including failures and tests.
Provider-side eligibility, quotas and plan rules always take precedence.
"""
from __future__ import annotations
import copy
import json
import os
import threading
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
import requests
from dotenv import load_dotenv
import boxing_feed as feed

API = "https://boxing-data-api.p.rapidapi.com"
HOST = "boxing-data-api.p.rapidapi.com"
MONTHLY_CAP = 30
LOCK = threading.Lock()
ALLOWED = {
    "fighters": "/v2/fighters/",
    "schedule": "/v2/fights/schedule",
    "results": "/v2/fights/",
}
SRC = "https://boxing-data.com/docs/"
LAST_ATTEMPT = "rapid_last_attempt"
LAST_SUCCESS = "rapid_last_success"
LAST_ERROR = "rapid_last_error"


class ApiAccessError(RuntimeError):
    pass


def config():
    load_dotenv(feed.BASE / ".env", override=True)
    key = os.getenv("BOXING_API_KEY", "").strip()
    if not key or key.upper().startswith(("DEIN_", "HIER_", "YOUR_")):
        key = ""
    enabled = os.getenv("BOXING_API_AUTO_SYNC", "true").strip().lower() in ("1","true","yes","on")
    return key, enabled


def month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def initialize():
    with feed.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS rapid_api_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            endpoint TEXT NOT NULL, created_at TEXT NOT NULL,
            http_status INTEGER, note TEXT
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS rapid_calls_month
            ON rapid_api_calls(month)""")
        db.execute("""CREATE TABLE IF NOT EXISTS rapid_fighter_cache(
            fighter_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS rapid_fighter_ids (
            remote_id TEXT PRIMARY KEY, local_id TEXT NOT NULL
        )""")


def usage():
    initialize()
    count = feed.one("SELECT COUNT(*) AS n FROM rapid_api_calls WHERE month=?",(month(),))["n"]
    return {"used":count,"limit":MONTHLY_CAP,"remaining":max(0,MONTHLY_CAP-count),
            "month":month(),"configured":bool(config()[0]),
            "auto_sync":config()[1],"last_success":feed.meta(LAST_SUCCESS),
            "last_attempt":feed.meta(LAST_ATTEMPT),
            "last_error":feed.meta(LAST_ERROR)}


def _provider_error(response):
    if response.status_code in (401, 403):
        if response.status_code == 403:
            return "Dieser API-Endpunkt ist im kostenlosen Tarif möglicherweise nicht verfügbar (HTTP 403)."
        return "API-Schlüssel ungültig oder kein aktiver API-Tarif (HTTP 401)."
    if response.status_code == 429:
        return "API-Kontingent oder Rate-Limit des Anbieters erreicht (HTTP 429)."
    return "Boxing Data API hat HTTP "+str(response.status_code)+" zurückgegeben."


def call(endpoint, params=None):
    """One billable request at most; reserve local budget BEFORE network call."""
    if endpoint not in ALLOWED:
        raise ValueError("Nicht erlaubter API-Endpunkt")
    key,_ = config()
    if not key:
        raise ApiAccessError("Kein API-Schlüssel. Trage BOXING_API_KEY in deine lokale .env ein.")
    initialize()
    # Serialized requests make the budget accurate even with concurrent admin actions.
    with LOCK:
        used = feed.one("SELECT COUNT(*) AS n FROM rapid_api_calls WHERE month=?",(month(),))["n"]
        if used >= MONTHLY_CAP:
            raise ApiAccessError("Sicherheitslimit erreicht: 30 Anfragen in diesem Monat. "
                                 "Bereits gespeicherte Daten bleiben verfügbar.")
        blocked = feed.meta("rapid_blocked_"+endpoint)
        if blocked == month():
            raise ApiAccessError("Dieser Endpunkt wurde diesen Monat gesperrt oder abgelehnt.")
        with feed.connect() as db:
            cur = db.execute("""INSERT INTO rapid_api_calls(month,endpoint,created_at)
                VALUES(?,?,?)""",(month(),endpoint,feed.utcnow()))
            call_id=cur.lastrowid
        # Never log the key or expose it in an HTTP response.
        try:
            response = requests.get(API+ALLOWED[endpoint],params=params or {},
                headers={"X-RapidAPI-Key":key,"X-RapidAPI-Host":HOST,
                         "Accept":"application/json"},timeout=9)
        except requests.RequestException as exc:
            with feed.connect() as db:
                db.execute("UPDATE rapid_api_calls SET note=? WHERE id=?",
                           ("Network error",call_id))
            raise ApiAccessError("Netzwerkfehler beim Datenanbieter.") from exc
        with feed.connect() as db:
            db.execute("UPDATE rapid_api_calls SET http_status=? WHERE id=?",
                       (response.status_code,call_id))
        if response.status_code != 200:
            if response.status_code in (403,429):
                feed.set_meta("rapid_blocked_"+endpoint,month())
            raise ApiAccessError(_provider_error(response))
        try:
            payload=response.json()
        except (ValueError,TypeError) as exc:
            raise ApiAccessError("Anbieter hat kein gültiges JSON zurückgegeben.") from exc
        if not isinstance(payload,dict):
            raise ApiAccessError("Unerwartetes JSON-Format")
        error = payload.get("error")
        if error and error != {}:
            raise ApiAccessError("Anbieter meldet einen Datenfehler.")
        if not isinstance(payload.get("data"),(list,dict)):
            raise ApiAccessError("API-Antwort enthält keine unterstützten Datensätze.")
        return payload["data"]


def _local_id(remote_id,name):
    rid = str(remote_id or "").strip()
    if not rid or not name:
        return None
    saved = feed.one("SELECT local_id FROM rapid_fighter_ids WHERE remote_id=?",(rid,))
    if saved:
        return saved["local_id"]
    # Prefer an explicitly reviewed or manually added local fighter over an
    # anonymous historic duplicate, but never guess between two candidates.
    preferred=feed.rows("""SELECT id FROM hub_fighters
        WHERE lower(trim(name))=lower(trim(?))
        AND (id LIKE 'reviewed-%' OR id LIKE 'manual-fighter-%')
        ORDER BY id""",(name,))
    internal=preferred[0]["id"] if len(preferred)==1 else "rapid-"+rid
    with feed.connect() as db:
        db.execute("""INSERT INTO rapid_fighter_ids(remote_id,local_id)
            VALUES(?,?) ON CONFLICT(remote_id) DO NOTHING""",(rid,internal))
    return feed.one("SELECT local_id FROM rapid_fighter_ids WHERE remote_id=?",(rid,))["local_id"]


def import_fighter(item,*,save_cache=True):
    if not isinstance(item,dict):
        return False
    rid = str(item.get("id") or "").strip()
    name = str(item.get("name") or item.get("full_name") or "").strip()
    if not rid or not name:
        return False
    internal = _local_id(rid,name)
    fighter = dict(item)
    fighter["id"] = internal
    feed.save_fighter(fighter)
    if save_cache:
        with feed.connect() as db:
            db.execute("""INSERT INTO rapid_fighter_cache(fighter_id,payload,imported_at)
              VALUES(?,?,?) ON CONFLICT(fighter_id) DO UPDATE SET
              payload=excluded.payload,imported_at=excluded.imported_at""",
              (internal,json.dumps(fighter,ensure_ascii=False),feed.utcnow()))
    with feed.connect() as db:
        db.execute("""INSERT INTO hub_sources(entity_id,source_url,reviewed_on,source_kind)
          VALUES(?,?,?,'rapidapi-profile')
          ON CONFLICT(entity_id) DO UPDATE SET
          source_url=excluded.source_url,reviewed_on=excluded.reviewed_on,
          source_kind=excluded.source_kind""",
          (internal,"https://boxing-data.com/docs/endpoints/fighters/",
           date.today().isoformat()))
    return True


def reapply_saved_profiles():
    """Curated seed data is loaded at every boot: keep newer cached API values."""
    initialize()
    for row in feed.rows("SELECT fighter_id,payload,imported_at FROM rapid_fighter_cache"):
        try:
            item=json.loads(row["payload"])
            if isinstance(item,dict):
                feed.save_fighter(item)
                with feed.connect() as db:
                    db.execute("""INSERT INTO hub_sources(entity_id,source_url,reviewed_on,source_kind)
                        VALUES(?,?,?,'rapidapi-profile')
                        ON CONFLICT(entity_id) DO UPDATE SET
                        source_url=excluded.source_url,reviewed_on=excluded.reviewed_on,
                        source_kind=excluded.source_kind""",
                        (row["fighter_id"],"https://boxing-data.com/docs/endpoints/fighters/",
                         row["imported_at"][:10]))
        except (ValueError,TypeError):
            continue


def _convert_fight(item,kind):
    if not isinstance(item,dict):
        return None
    rid=str(item.get("id") or "").strip()
    date_str=str(item.get("date") or "")
    status=str(item.get("status") or "").upper()
    if not rid or len(date_str)<10:
        return None
    try:
        day=date.fromisoformat(date_str[:10])
    except ValueError:
        return None
    if kind=="schedule" and (status not in ("NOT_STARTED","LIVE") or day < date.today()):
        return None
    if kind=="results" and (status!="FINISHED" or day > date.today()):
        return None
    incoming=item.get("fighters") or {}
    if not isinstance(incoming,dict):
        return None
    pair=[]
    for k in ("fighter_1","fighter_2"):
        f=incoming.get(k)
        if not isinstance(f,dict):
            return None
        name=str(f.get("full_name") or f.get("name") or "").strip()
        fid=_local_id(f.get("fighter_id"),name)
        if not fid or not name:
            return None
        pair.append({**f,"fighter_id":fid,"full_name":name})
    if pair[0]["fighter_id"]==pair[1]["fighter_id"] or not feed._has_two_boxers(
        pair[0]["full_name"],pair[1]["full_name"]):
        return None
    event=item.get("event") if isinstance(item.get("event"),dict) else {}
    external_event=str(event.get("id") or "").strip()
    converted=copy.deepcopy(item)
    converted["id"]="rapid-"+rid
    converted["fighters"]={"fighter_1":pair[0],"fighter_2":pair[1]}
    converted["event"]={**event,"id":"rapid-event-"+external_event if external_event else ""}
    return converted


def _import_bouts(items,kind):
    if not isinstance(items,list):
        raise ApiAccessError("Kampfliste hat ein unerwartetes Format.")
    bouts=[]
    events={}
    for item in items:
        converted=_convert_fight(item,kind)
        if converted is None:
            continue
        bouts.append(converted)
        event=converted.get("event",{})
        if event.get("id"):
            events[event["id"]]={
                "id":event["id"],
                "title":event.get("title") or converted.get("title"),
                "date":event.get("date") or converted.get("date"),
                "venue":converted.get("venue") or event.get("venue"),
                "location":converted.get("location") or event.get("location"),
            }
    if bouts:
        feed.save_fights(bouts)
    if events:
        feed.save_events(list(events.values()))
    with feed.connect() as db:
        for fight in bouts:
            db.execute("""INSERT INTO hub_sources(
               entity_id,source_url,reviewed_on,source_kind,time_note)
               VALUES(?,?,?,?,?)
               ON CONFLICT(entity_id) DO UPDATE SET
               source_url=excluded.source_url,reviewed_on=excluded.reviewed_on,
               source_kind=excluded.source_kind""",
               (fight["id"],"https://boxing-data.com/docs/endpoints/fights/",
                date.today().isoformat(),"rapidapi-"+kind,
                "Vom Anbieter gemeldete Zeit; Zeitzone und Ringwalk nicht garantiert"))
    return len(bouts)


def verify():
    """One explicit admin test request: no automatic retries."""
    data=call("fighters",{"name":"Tyson Fury","page_size":10,"page_num":1})
    if not isinstance(data,list):
        raise ApiAccessError("Fighter-Endpunkt liefert keine Liste.")
    count=sum(import_fighter(f) for f in data if isinstance(f,dict))
    from fightbase_admin import apply_manual_records
    apply_manual_records()
    feed.set_meta(LAST_SUCCESS,feed.utcnow())
    feed.set_meta(LAST_ERROR,"")
    return {"profiles":count,"message":"Verbindung erfolgreich; "+str(count)+" Boxerprofile eingelesen."}


def synchronize(force=False):
    """At most 5 API requests per run; weekly by default.

    Failing or forbidden endpoints don't destroy cached local data.
    """
    key,enabled=config()
    if not key:
        return {"requested":0,"fights":0,"profiles":0,"errors":["Kein API-Schlüssel."]}
    if not force and not enabled:
        return {"requested":0,"fights":0,"profiles":0,"errors":[]}
    previous=feed.meta(LAST_ATTEMPT)
    if previous and not force:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(previous)<timedelta(days=7):
                return {"requested":0,"fights":0,"profiles":0,"errors":[]}
        except ValueError:
            pass
    feed.set_meta(LAST_ATTEMPT,feed.utcnow())
    before=usage()["used"]
    errors=[]
    bouts=0
    profiles=0
    discovered=[]
    try:
        items=call("schedule",{"days":30,"date_sort":"ASC","page_size":30,"page_num":1})
        bouts+=_import_bouts(items,"schedule")
        if isinstance(items,list):
            for item in items:
                if isinstance(item,dict) and isinstance(item.get("fighters"),dict):
                    for f in item["fighters"].values():
                        if isinstance(f,dict) and f.get("fighter_id") and f.get("full_name"):
                            discovered.append((str(f["fighter_id"]),str(f["full_name"])))
    except ApiAccessError as exc:
        errors.append("Kampfplan: "+str(exc))
    try:
        items=call("results",{"date_sort":"DESC","page_size":30,"page_num":1})
        bouts+=_import_bouts(items,"results")
    except ApiAccessError as exc:
        errors.append("Ergebnisse: "+str(exc))
    try:
        items=call("fighters",{"page_size":30,"page_num":1})
        if not isinstance(items,list):
            raise ApiAccessError("Boxerliste liefert keine Liste.")
        profiles+=sum(import_fighter(f) for f in items if isinstance(f,dict))
    except ApiAccessError as exc:
        errors.append("Boxer: "+str(exc))
    # Optional enrichment of up to two fighters from upcoming fights per run.
    for fid,name in list(dict.fromkeys(discovered))[:2]:
        try:
            # A narrow name search is supported on the free fighter-list route.
            items=call("fighters",{"name":name,"page_size":10,"page_num":1})
            if isinstance(items,list):
                profiles+=sum(import_fighter(f) for f in items
                              if isinstance(f,dict) and str(f.get("name","")).casefold()==name.casefold())
        except ApiAccessError as exc:
            errors.append("Boxerdetails: "+str(exc))
            break
    from fightbase_admin import apply_manual_records
    apply_manual_records()
    used=usage()["used"]-before
    if used:
        feed.set_meta(LAST_ERROR," | ".join(errors[:3]))
        if bouts or profiles:
            feed.set_meta(LAST_SUCCESS,feed.utcnow())
    return {"requested":used,"fights":bouts,"profiles":profiles,"errors":errors}


def refresh_if_due():
    """Only the existing background sync calls this, never page rendering."""
    if not config()[0] or not config()[1]:
        return
    synchronize(force=False)
