"""Fightbase: Boxing Data API cache, profiles and automatic synchronization."""
from __future__ import annotations
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
DB = BASE / "fightbase.db"
API = "https://www.thesportsdb.com/api/v1/json/123"
HOST = "www.thesportsdb.com"
DIVISIONS = ["Heavyweight","Cruiserweight","Light Heavyweight","Super Middleweight","Middleweight","Super Welterweight","Welterweight","Super Lightweight","Lightweight","Super Featherweight","Featherweight","Super Bantamweight","Bantamweight","Super Flyweight","Flyweight","Light Flyweight","Minimumweight"]
LOCK = threading.Lock()
RUNNING = False

def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def settings():
    """TheSportsDB v1 is free and uses the public key 123."""
    load_dotenv(BASE / ".env")
    try:
        minutes = max(60, int(os.getenv("FEED_REFRESH_MINUTES", "360")))
    except ValueError:
        minutes = 360
    return "FREE", minutes, 1


def connect():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=20000")
    return c

def init_feed():
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS hub_meta(
            key TEXT PRIMARY KEY, value TEXT NOT NULL)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hub_fights(
            id TEXT PRIMARY KEY, fight_date TEXT, title TEXT, status TEXT,
            a_id TEXT, b_id TEXT, a_name TEXT, b_name TEXT,
            winner_id TEXT, outcome TEXT, result_round TEXT,
            division TEXT, event_id TEXT, event_title TEXT,
            venue TEXT, location TEXT, rounds INTEGER, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hub_fighters(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, age INTEGER,
            wins INTEGER, losses INTEGER, draws INTEGER, ko_wins INTEGER,
            nationality TEXT, division TEXT, stance TEXT, height TEXT,
            nickname TEXT, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hub_events(
            id TEXT PRIMARY KEY, title TEXT, event_date TEXT,
            venue TEXT, location TEXT, updated_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hub_images(
            fighter_id TEXT PRIMARY KEY, image_url TEXT,
            source_url TEXT, checked_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS hub_rankings(
            page INTEGER PRIMARY KEY, content TEXT NOT NULL, checked_at TEXT)""")
        c.execute("CREATE INDEX IF NOT EXISTS hub_date ON hub_fights(fight_date)")
        c.execute("CREATE INDEX IF NOT EXISTS hub_name ON hub_fighters(name)")

def meta(key, default=""):
    with connect() as c:
        row = c.execute("SELECT value FROM hub_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default

def set_meta(key, value):
    with connect() as c:
        c.execute("""INSERT INTO hub_meta(key,value) VALUES (?,?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (key, str(value)))

def get(path, params=None):
    """Fetch only TheSportsDB public v1 endpoints; never use RapidAPI."""
    if path not in ("/eventsday.php", "/searchplayers.php"):
        raise ValueError("Kostenlose API unterstützt diesen Endpunkt nicht")
    response = requests.get(API + path, params=params or {}, timeout=15,
                            headers={"Accept":"application/json","User-Agent":"FightbaseStudent/1.0"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Unerwartete Antwort von TheSportsDB")
    return payload


def pages(path, options):
    raise ValueError("Paginierung ist in diesem kostenlosen Feed nicht verfügbar")


def txt(value):
    return str(value).strip() if value is not None else ""

def num(value):
    try:
        return None if isinstance(value,bool) or value is None else int(value)
    except (TypeError,ValueError):
        return None

def save_fighter(item):
    if not isinstance(item,dict):
        return
    fid, name = txt(item.get("id")), txt(item.get("name") or item.get("full_name"))
    if not fid or not name:
        return
    stats = item.get("stats") if isinstance(item.get("stats"),dict) else {}
    division = item.get("division") if isinstance(item.get("division"),dict) else {}
    with connect() as c:
        c.execute("""INSERT INTO hub_fighters(id,name,age,wins,losses,draws,ko_wins,nationality,division,stance,height,nickname,updated_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
         ON CONFLICT(id) DO UPDATE SET
         name=excluded.name,
         age=COALESCE(excluded.age,hub_fighters.age),
         wins=COALESCE(excluded.wins,hub_fighters.wins),
         losses=COALESCE(excluded.losses,hub_fighters.losses),
         draws=COALESCE(excluded.draws,hub_fighters.draws),
         ko_wins=COALESCE(excluded.ko_wins,hub_fighters.ko_wins),
         nationality=COALESCE(NULLIF(excluded.nationality,''),hub_fighters.nationality),
         division=COALESCE(NULLIF(excluded.division,''),hub_fighters.division),
         stance=COALESCE(NULLIF(excluded.stance,''),hub_fighters.stance),
         height=COALESCE(NULLIF(excluded.height,''),hub_fighters.height),
         nickname=COALESCE(NULLIF(excluded.nickname,''),hub_fighters.nickname),
         updated_at=excluded.updated_at""",
         (fid,name,num(item.get("age")),num(stats.get("wins")),num(stats.get("losses")),
          num(stats.get("draws")),num(stats.get("ko_wins")),
          txt(item.get("nationality")),txt(division.get("name")),txt(item.get("stance")),
          txt(item.get("height")),txt(item.get("nickname") or item.get("alias")),utcnow()))

def add_stub(c, item):
    if not isinstance(item,dict):
        return
    fid=txt(item.get("fighter_id"))
    name=txt(item.get("full_name") or item.get("name") or item.get("fighter_name"))
    if fid and name:
        c.execute("""INSERT INTO hub_fighters(id,name,updated_at) VALUES (?,?,?)
           ON CONFLICT(id) DO UPDATE SET name=excluded.name""",(fid,name,utcnow()))

def save_fights(records):
    with connect() as c:
        for item in records:
            fid=txt(item.get("id"))
            if not fid:
                continue
            boxers=item.get("fighters") if isinstance(item.get("fighters"),dict) else {}
            a=boxers.get("fighter_1") if isinstance(boxers.get("fighter_1"),dict) else {}
            b=boxers.get("fighter_2") if isinstance(boxers.get("fighter_2"),dict) else {}
            event=item.get("event") if isinstance(item.get("event"),dict) else {}
            division=item.get("division") if isinstance(item.get("division"),dict) else {}
            result=item.get("results") if isinstance(item.get("results"),dict) else {}
            add_stub(c,a)
            add_stub(c,b)
            status=txt(item.get("status")).upper()
            if status not in ("NOT_STARTED","LIVE","FINISHED"):
                status="UNKNOWN"
            winner=txt(a.get("fighter_id") if a.get("winner") is True else
                       b.get("fighter_id") if b.get("winner") is True else "")
            c.execute("""INSERT INTO hub_fights VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET
              fight_date=excluded.fight_date,title=excluded.title,status=excluded.status,
              a_id=excluded.a_id,b_id=excluded.b_id,
              a_name=excluded.a_name,b_name=excluded.b_name,
              winner_id=excluded.winner_id,outcome=excluded.outcome,
              result_round=excluded.result_round,division=excluded.division,
              event_id=excluded.event_id,event_title=excluded.event_title,
              venue=excluded.venue,location=excluded.location,
              rounds=excluded.rounds,updated_at=excluded.updated_at""",
              (fid,txt(item.get("date")),txt(item.get("title")),status,
               txt(a.get("fighter_id")),txt(b.get("fighter_id")),
               txt(a.get("full_name") or a.get("name")),txt(b.get("full_name") or b.get("name")),
               winner,txt(result.get("outcome")),txt(result.get("round")),
               txt(division.get("name")),txt(event.get("id")),txt(event.get("title")),
               txt(item.get("venue") or event.get("venue")),
               txt(item.get("location") or event.get("location")),
               num(item.get("scheduled_rounds")),utcnow()))

def save_events(records):
    with connect() as c:
        for item in records:
            fid=txt(item.get("id"))
            if fid:
                c.execute("""INSERT INTO hub_events VALUES (?,?,?,?,?,?)
                 ON CONFLICT(id) DO UPDATE SET
                 title=excluded.title,event_date=excluded.event_date,
                 venue=excluded.venue,location=excluded.location,
                 updated_at=excluded.updated_at""",
                 (fid,txt(item.get("title")),txt(item.get("date")),
                  txt(item.get("venue")),txt(item.get("location")),utcnow()))

def _is_boxing(item):
    """Accept explicit boxing, reject MMA, kickboxing and ONE events."""
    sport = txt(item.get("strSport")).casefold()
    details = " ".join(txt(item.get(k)) for k in (
        "strLeague", "strEvent", "strDescriptionEN")).casefold()
    if sport not in ("fighting", "boxing"):
        return False
    if any(word in details for word in (
        "kickboxing", "muay thai", "mma", "mixed martial arts",
        "one championship", "one the inner circle", "ufc", "bellator",
        "pfl", "grappling", "karate")):
        return False
    return any(word in details for word in (
        "boxing", "boxe", "boxen", "wbc", "wba", "ibf", "wbo",
        "professional boxer"))

def _has_two_boxers(a, b):
    invalid = {"", "tba", "tbd", "unknown", "noch offen", "to be announced"}
    left, right = txt(a).casefold(), txt(b).casefold()
    return left not in invalid and right not in invalid and left != right

def _split_match(item):
    left = txt(item.get("strHomeTeam"))
    right = txt(item.get("strAwayTeam"))
    title = txt(item.get("strEvent"))
    if left and right:
        return left, right
    for separator in (" vs. ", " vs ", " v ", " - "):
        import re
        pieces = re.split(re.escape(separator), title, maxsplit=1, flags=re.I)
        if len(pieces) == 2:
            return pieces[0].strip(), pieces[1].strip()
    return "", ""

def _store_free_event(item):
    event_id = txt(item.get("idEvent"))
    if not event_id or not _is_boxing(item):
        return
    title = txt(item.get("strEvent"))
    a, b = _split_match(item)
    # Unknown participants: keep event, do not create a false fight.
    day = txt(item.get("dateEvent"))
    stamp = (day + "T" + txt(item.get("strTime"))) if day else ""
    status = "FINISHED" if day and day < date.today().isoformat() else "NOT_STARTED"
    venue = txt(item.get("strVenue"))
    league = txt(item.get("strLeague"))
    with connect() as c:
        c.execute("""INSERT INTO hub_events(id,title,event_date,venue,location,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            title=excluded.title,event_date=excluded.event_date,
            venue=excluded.venue,location=excluded.location,
            updated_at=excluded.updated_at""",
            ("tsdb-"+event_id,title or league,day,venue,
             txt(item.get("strCountry")),utcnow()))
        for player in (a,b):
            if player:
                identifier="tsdb-"+player.casefold().strip()
                c.execute("""INSERT INTO hub_fighters(id,name,updated_at)
                    VALUES(?,?,?) ON CONFLICT(id) DO NOTHING""",(identifier,player,utcnow()))
        if not _has_two_boxers(a, b):
            return
        c.execute("""INSERT INTO hub_fights
            (id,fight_date,title,status,a_id,b_id,a_name,b_name,
             division,event_id,event_title,venue,location,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
            fight_date=excluded.fight_date,title=excluded.title,
            status=excluded.status,a_id=excluded.a_id,b_id=excluded.b_id,
            a_name=excluded.a_name,b_name=excluded.b_name,
            event_id=excluded.event_id,event_title=excluded.event_title,
            venue=excluded.venue,location=excluded.location,
            updated_at=excluded.updated_at""",
            ("tsdb-"+event_id,stamp,title,status,
             "tsdb-"+a.casefold() if a else "",
             "tsdb-"+b.casefold() if b else "",a,b,"",
             "tsdb-"+event_id,league,venue,txt(item.get("strCountry")),utcnow()))

def sync():
    """Free daily feed; coverage can be sparse, never fabricate fights."""
    from datetime import timedelta
    errors=[]
    scanned=0
    # Seven dates gives modest daily coverage without a paid subscription.
    for offset in range(-2,8):
        day=(date.today()+timedelta(days=offset)).isoformat()
        try:
            payload=get("/eventsday.php",{"d":day,"s":"Fighting"})
            for event in payload.get("events") or []:
                if isinstance(event,dict) and _is_boxing(event):
                    _store_free_event(event)
                    scanned+=1
        except (requests.RequestException,ValueError,TypeError) as exc:
            errors.append(day+": "+str(exc)[:90])
    if len(errors)<10:
        set_meta("last_success",utcnow())
    set_meta("error"," | ".join(errors[:2]) if errors else "")
    set_meta("feed_note","Kostenloser Feed: "+str(scanned)+" Boxeinträge gefunden; keine Vollständigkeitsgarantie.")


def _worker():
    global RUNNING
    try:
        sync()
    finally:
        RUNNING=False
        LOCK.release()

def trigger_sync(force=False):
    global RUNNING
    key, minutes, _=settings()
    if not key:
        return False
    last=meta("last_attempt")
    if last and not force:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(last)<timedelta(minutes=minutes):
                return False
        except ValueError:
            pass
    if not LOCK.acquire(blocking=False):
        return False
    set_meta("last_attempt",utcnow())
    RUNNING=True
    threading.Thread(target=_worker,name="fightbase-sync",daemon=True).start()
    return True

def start_scheduler():
    import time
    def loop():
        while True:
            trigger_sync()
            time.sleep(900)
    threading.Thread(target=loop,name="fightbase-scheduler",daemon=True).start()

def status():
    return dict(configured=True,syncing=RUNNING,
        last_success=meta("last_success"),error=meta("error"),
        note=meta("feed_note","Kostenlose TheSportsDB API aktiv. Boxabdeckung begrenzt."))


def rows(sql,params=()):
    with connect() as c:
        return c.execute(sql,params).fetchall()

def one(sql,params=()):
    with connect() as c:
        return c.execute(sql,params).fetchone()

def upcoming(limit=65):
    return rows("""SELECT * FROM hub_fights
       WHERE substr(fight_date,1,10)>=? AND status IN ('NOT_STARTED','LIVE')
       AND trim(COALESCE(a_name,'')) != '' AND trim(COALESCE(b_name,'')) != ''
       AND lower(trim(a_name)) NOT IN ('tba','tbd','unknown','noch offen')
       AND lower(trim(b_name)) NOT IN ('tba','tbd','unknown','noch offen')
       AND lower(trim(a_name)) != lower(trim(b_name))
       ORDER BY fight_date ASC LIMIT ?""",(date.today().isoformat(),limit))

def results(limit=60):
    since=(date.today()-timedelta(days=365)).isoformat()
    return rows("""SELECT * FROM hub_fights WHERE status='FINISHED'
       AND substr(fight_date,1,10)>=?
       AND trim(COALESCE(a_name,'')) != '' AND trim(COALESCE(b_name,'')) != ''
       AND lower(trim(a_name)) NOT IN ('tba','tbd','unknown','noch offen')
       AND lower(trim(b_name)) NOT IN ('tba','tbd','unknown','noch offen')
       ORDER BY fight_date DESC LIMIT ?""",(since,limit))

def events():
    return rows("""SELECT * FROM hub_events
       WHERE substr(event_date,1,10)>=?
       AND (lower(title) LIKE '%boxing%' OR lower(title) LIKE '%boxe%'
            OR lower(title) LIKE '%wbc%' OR lower(title) LIKE '%wba%'
            OR lower(title) LIKE '%ibf%' OR lower(title) LIKE '%wbo%')
       AND lower(title) NOT LIKE '%kickboxing%'
       AND lower(title) NOT LIKE '%one championship%'
       AND lower(title) NOT LIKE '%one the inner circle%'
       ORDER BY event_date ASC LIMIT 50""",(date.today().isoformat(),))

def fighters(search=""):
    if search:
        return rows("""SELECT * FROM hub_fighters WHERE name LIKE ? COLLATE NOCASE
          ORDER BY CASE WHEN wins IS NULL THEN 1 ELSE 0 END,name LIMIT 80""",("%"+search+"%",))
    return rows("""SELECT * FROM hub_fighters
       ORDER BY CASE WHEN wins IS NULL THEN 1 ELSE 0 END,
       COALESCE(wins,0) DESC,name LIMIT 80""")

def search_fighter(term):
    """Search free sports profiles, avoiding any fabricated boxer statistics."""
    if len(term)<3:
        return
    marker="free-search:"+term.casefold()
    try:
        if datetime.now(timezone.utc)-datetime.fromisoformat(meta(marker))<timedelta(hours=12):
            return
    except ValueError:
        pass
    try:
        payload=get("/searchplayers.php",{"p":term})
        for item in payload.get("player") or []:
            if not isinstance(item,dict):
                continue
            description=txt(item.get("strDescriptionEN")).lower()
            sport=txt(item.get("strSport")).lower()
            if sport not in ("fighting","boxing") or "box" not in description:
                continue
            fid=txt(item.get("idPlayer"))
            name=txt(item.get("strPlayer"))
            if not fid or not name:
                continue
            born=txt(item.get("dateBorn"))
            age=None
            try:
                born_date=date.fromisoformat(born)
                age=(date.today().year-born_date.year)-(
                    (date.today().month,date.today().day)<(born_date.month,born_date.day))
            except ValueError:
                pass
            save_fighter({"id":"tsdb-p-"+fid,"name":name,"age":age,
                "nationality":item.get("strNationality"),
                "division":{"name":txt(item.get("strPosition"))}})
        set_meta(marker,utcnow())
    except (requests.RequestException,ValueError,TypeError):
        pass


def fighter_detail(fid):
    return one("SELECT * FROM hub_fighters WHERE id=?",(fid,))


def event_fights(event_id):
    if not event_id or len(event_id)>80:
        return []
    return rows("SELECT * FROM hub_fights WHERE event_id=? ORDER BY fight_date",(event_id,))


def rankings(page=1):
    # No reliable, current, free WBA/WBC/IBF/WBO ranking source.
    return []


def photo(fid,name):
    """One cached picture per fighter; not guaranteed to be a recent ring photograph."""
    if not fid or not name:
        return {"url":None,"source":None}
    # Respect photos previously selected in the old Fightbase comparison.
    try:
        norm=re.sub(r"\s+"," ",name.casefold()).strip()
        saved=one("SELECT candidates,selected_index FROM photo_choices WHERE fighter_key=?",(norm,))
        if saved:
            photos=json.loads(saved["candidates"])
            selected=photos[int(saved["selected_index"])]
            if selected.get("url"):
                return {"url":selected["url"],"source":selected.get("source")}
    except (sqlite3.OperationalError,ValueError,TypeError,IndexError):
        pass
    cached=one("SELECT * FROM hub_images WHERE fighter_id=?",(fid,))
    if cached:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(cached["checked_at"])<timedelta(days=14):
                return {"url":cached["image_url"],"source":cached["source_url"]}
        except ValueError:
            pass
    image_url=source_url=None
    for title in (name,name+" (boxer)"):
        try:
            response=requests.get("https://en.wikipedia.org/api/rest_v1/page/summary/"+
                 quote(title.replace(" ","_"),safe=""),timeout=7,
                 headers={"User-Agent":"FightbaseEducational/1.0 (local student project)"})
            if response.status_code!=200:
                continue
            info=response.json()
            desc=(str(info.get("description") or "")+" "+str(info.get("extract") or "")).lower()
            real_name=str(info.get("title") or "").casefold()
            if name.casefold() not in real_name or not any(
                word in desc for word in ("boxer","boxing","pugilist")
            ):
                continue
            candidate=(info.get("thumbnail") or {}).get("source")
            source=((info.get("content_urls") or {}).get("desktop") or {}).get("page")
            if isinstance(candidate,str) and candidate.startswith("https://"):
                image_url,source_url=candidate,source
                break
        except (requests.RequestException,ValueError):
            pass
    with connect() as c:
        c.execute("""INSERT INTO hub_images VALUES (?,?,?,?)
        ON CONFLICT(fighter_id) DO UPDATE SET
        image_url=excluded.image_url,source_url=excluded.source_url,
        checked_at=excluded.checked_at""",(fid,image_url,source_url,utcnow()))
    return {"url":image_url,"source":source_url}
