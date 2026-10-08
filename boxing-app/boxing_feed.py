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
API = "https://boxing-data-api.p.rapidapi.com"
HOST = "boxing-data-api.p.rapidapi.com"
DIVISIONS = ["Heavyweight","Cruiserweight","Light Heavyweight","Super Middleweight","Middleweight","Super Welterweight","Welterweight","Super Lightweight","Lightweight","Super Featherweight","Featherweight","Super Bantamweight","Bantamweight","Super Flyweight","Flyweight","Light Flyweight","Minimumweight"]
LOCK = threading.Lock()
RUNNING = False

def utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def settings():
    load_dotenv(BASE / ".env", override=True)
    key = os.getenv("BOXING_API_KEY", "").strip()
    if key.upper().startswith(("DEIN_", "YOUR_", "HIER_")):
        key = ""
    try:
        minutes = max(15, int(os.getenv("FEED_REFRESH_MINUTES", "180")))
        pages = min(5, max(1, int(os.getenv("FEED_PAGES", "2"))))
    except ValueError:
        minutes, pages = 180, 2
    return key, minutes, pages

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
    key, _, _ = settings()
    if not key:
        raise RuntimeError("BOXING_API_KEY fehlt. Bitte boxing-app/.env konfigurieren.")
    response = requests.get(API + path, params=params or {}, timeout=15,
        headers={"X-RapidAPI-Key":key,"X-RapidAPI-Host":HOST,"Accept":"application/json"})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload,dict) or not isinstance(payload.get("data"),(dict,list)):
        raise ValueError("Unerwartete Antwort der Boxing Data API")
    if payload.get("error"):
        raise ValueError(str(payload["error"])[:150])
    return payload

def pages(path, options):
    _, _, maximum = settings()
    records = []
    for page in range(1, maximum+1):
        response = get(path, {**options,"page_num":page})
        data = response["data"]
        if not isinstance(data,list):
            raise ValueError("API-Liste erwartet")
        records.extend(x for x in data if isinstance(x,dict))
        total = (response.get("pagination") or {}).get("total_pages")
        if not data or isinstance(total,int) and total and page >= total:
            break
    return records

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

def sync():
    jobs=[
      ("Kampfplan",lambda:save_fights(pages("/v2/fights/schedule",{"days":90,"date_sort":"ASC","page_size":50}))),
      ("Ergebnisse",lambda:save_fights(pages("/v2/fights/",{"date_sort":"DESC","page_size":50}))),
      ("Veranstaltungen",lambda:save_events(pages("/v2/events/schedule",{"days":90,"date_sort":"ASC","page_size":50}))),
      ("Boxer",lambda:[save_fighter(f) for f in pages("/v2/fighters/",{"page_size":50})])
    ]
    errors=[]
    successes=0
    for name,job in jobs:
        try:
            job()
            successes+=1
        except (requests.RequestException,ValueError,RuntimeError,TypeError) as e:
            errors.append(name+": "+str(e)[:150])
    if successes:
        set_meta("last_success",utcnow())
    set_meta("error"," | ".join(errors))

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
    key,_,_=settings()
    return dict(configured=bool(key),syncing=RUNNING,
        last_success=meta("last_success"),error=meta("error"))

def rows(sql,params=()):
    with connect() as c:
        return c.execute(sql,params).fetchall()

def one(sql,params=()):
    with connect() as c:
        return c.execute(sql,params).fetchone()

def upcoming(limit=65):
    return rows("""SELECT * FROM hub_fights
       WHERE substr(fight_date,1,10)>=? AND status IN ('NOT_STARTED','LIVE')
       ORDER BY fight_date ASC LIMIT ?""",(date.today().isoformat(),limit))

def results(limit=60):
    since=(date.today()-timedelta(days=365)).isoformat()
    return rows("""SELECT * FROM hub_fights WHERE status='FINISHED'
       AND substr(fight_date,1,10)>=? ORDER BY fight_date DESC LIMIT ?""",(since,limit))

def events():
    return rows("""SELECT * FROM hub_events WHERE substr(event_date,1,10)>=?
       ORDER BY event_date ASC LIMIT 50""",(date.today().isoformat(),))

def fighters(search=""):
    if search:
        return rows("""SELECT * FROM hub_fighters WHERE name LIKE ? COLLATE NOCASE
          ORDER BY CASE WHEN wins IS NULL THEN 1 ELSE 0 END,name LIMIT 80""",("%"+search+"%",))
    return rows("""SELECT * FROM hub_fighters
       ORDER BY CASE WHEN wins IS NULL THEN 1 ELSE 0 END,
       COALESCE(wins,0) DESC,name LIMIT 80""")

def search_fighter(term):
    if len(term)<3 or not settings()[0]:
        return
    marker="search:"+term.casefold()
    try:
        if datetime.now(timezone.utc)-datetime.fromisoformat(meta(marker))<timedelta(hours=8):
            return
    except ValueError:
        pass
    try:
        for person in get("/v2/fighters/",{"name":term,"page_size":50})["data"]:
            save_fighter(person)
        set_meta(marker,utcnow())
    except (requests.RequestException,RuntimeError,ValueError,TypeError):
        pass

def fighter_detail(fid):
    cached=one("SELECT * FROM hub_fighters WHERE id=?",(fid,))
    if not cached:
        return None
    stale=True
    try:
        stale=(datetime.now(timezone.utc)-datetime.fromisoformat(cached["updated_at"]))>timedelta(hours=24)
    except (ValueError,TypeError):
        pass
    if settings()[0] and (cached["wins"] is None or stale):
        try:
            person=get("/v2/fighters/"+quote(fid,safe=""))["data"]
            if isinstance(person,dict):
                save_fighter(person)
        except (requests.RequestException,RuntimeError,ValueError,TypeError):
            pass
    return one("SELECT * FROM hub_fighters WHERE id=?",(fid,))

def event_fights(event_id):
    if not event_id or len(event_id)>80:
        return []
    marker="event:"+event_id
    stale=True
    try:
        stale=(datetime.now(timezone.utc)-datetime.fromisoformat(meta(marker)))>timedelta(hours=6)
    except ValueError:
        pass
    if stale and settings()[0]:
        try:
            save_fights(get("/v2/fights/",{"event_id":event_id,"page_size":50})["data"])
            set_meta(marker,utcnow())
        except (requests.RequestException,RuntimeError,ValueError,TypeError):
            pass
    return rows("SELECT * FROM hub_fights WHERE event_id=? ORDER BY fight_date",(event_id,))

def rankings(page=1):
    if page not in range(1,18):
        return []
    cached=one("SELECT * FROM hub_rankings WHERE page=?",(page,))
    if cached:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(cached["checked_at"])<timedelta(hours=24):
                return json.loads(cached["content"])
        except (ValueError,TypeError):
            pass
    if not settings()[0]:
        return json.loads(cached["content"]) if cached else []
    try:
        data=get("/v2/rankings/",{"page_num":page})["data"]
        if not isinstance(data,list):
            return []
        with connect() as c:
            c.execute("""INSERT INTO hub_rankings VALUES (?,?,?)
               ON CONFLICT(page) DO UPDATE SET content=excluded.content,checked_at=excluded.checked_at""",
               (page,json.dumps(data),utcnow()))
            for org in data:
                for item in (org.get("rankings") or [])+(org.get("champions") or []):
                    add_stub(c,item)
        return data
    except (requests.RequestException,RuntimeError,ValueError,TypeError):
        return json.loads(cached["content"]) if cached else []

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
