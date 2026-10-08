"""Use only identity-checked Wikidata boxer portraits.

Wikidata P18 images belong to a specific verified boxer entity. Wrong,
ambiguous or unavailable photos are never replaced by random Commons hits.
Image dates are not guaranteed to be current.
"""
import re
import unicodedata
from datetime import datetime,timedelta,timezone
from concurrent.futures import ThreadPoolExecutor
import threading
from urllib.parse import quote
import requests

API="https://www.wikidata.org/w/api.php"
PHOTO_POOL=ThreadPoolExecutor(max_workers=3,thread_name_prefix="fightbase-photos")
PHOTO_PENDING=set()
PHOTO_LOCK=threading.Lock()
HEADERS={"User-Agent":"FightbaseEducation/2.0 (GitHub s1naoui/Fightbase student project)",
         "Accept":"application/json"}

def normalize(name):
    s=unicodedata.normalize("NFKD",name or "")
    s="".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+"," ",s.casefold()).strip()

def claim_id(claim):
    try:
        return claim["mainsnak"]["datavalue"]["value"]["id"]
    except (KeyError,TypeError):
        return None

def choose_photo(name, search, entities):
    exact=[item for item in search
           if normalize(item.get("label"))==normalize(name)
           and "box" in item.get("description","").casefold()]
    if len(exact)!=1:
        return None
    person=entities.get(exact[0].get("id"),{})
    occupations={claim_id(x) for x in person.get("claims",{}).get("P106",[])}
    if "Q11338576" not in occupations:
        return None
    try:
        filename=person["claims"]["P18"][0]["mainsnak"]["datavalue"]["value"]
    except (KeyError,IndexError,TypeError):
        return None
    if not isinstance(filename,str) or not filename:
        return None
    key=quote(filename.replace(" ","_"),safe="")
    return {"url":"https://commons.wikimedia.org/wiki/Special:FilePath/"+key+"?width=900",
            "source":"https://commons.wikimedia.org/wiki/File:"+key,
            "verified":True}

def photo_from_cache(fighter_id):
    from boxing_feed import connect
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS hub_verified_images(
            fighter_id TEXT PRIMARY KEY,image_url TEXT,source_url TEXT,
            checked_at TEXT NOT NULL)""")
        return db.execute("SELECT * FROM hub_verified_images WHERE fighter_id=?",
                          (fighter_id,)).fetchone()

def quick_verified_photo(fighter_id,name):
    """Return cached image immediately and queue bounded background lookup."""
    if not fighter_id or not name:
        return {"url":None,"source":None,"pending":False}
    cached=photo_from_cache(fighter_id)
    if cached:
        try:
            if datetime.now(timezone.utc)-datetime.fromisoformat(cached["checked_at"])<timedelta(days=30):
                return {"url":cached["image_url"],"source":cached["source_url"],
                        "pending":False}
        except ValueError:
            pass
    with PHOTO_LOCK:
        if fighter_id not in PHOTO_PENDING and len(PHOTO_PENDING)<24:
            PHOTO_PENDING.add(fighter_id)
            PHOTO_POOL.submit(_do_photo_lookup,fighter_id,name)
    return {"url":cached["image_url"] if cached else None,
            "source":cached["source_url"] if cached else None,"pending":True}

def _do_photo_lookup(fighter_id,name):
    try:
        verified_photo(fighter_id,name)
    finally:
        with PHOTO_LOCK:
            PHOTO_PENDING.discard(fighter_id)

def fetch(params):
    result=requests.get(API,params={"format":"json",**params},
                        headers=HEADERS,timeout=3)
    result.raise_for_status()
    return result.json()

def verified_photo(fighter_id,name):
    from boxing_feed import connect
    if not fighter_id or not name:
        return {"url":None,"source":None}
    with connect() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS hub_verified_images(
         fighter_id TEXT PRIMARY KEY,image_url TEXT,source_url TEXT,
         checked_at TEXT NOT NULL)""")
        cached=c.execute("SELECT * FROM hub_verified_images WHERE fighter_id=?",
                         (fighter_id,)).fetchone()
    if cached:
        try:
            checked=datetime.fromisoformat(cached["checked_at"])
            if datetime.now(timezone.utc)-checked<timedelta(days=30):
                return {"url":cached["image_url"],"source":cached["source_url"],
                        "verified":bool(cached["image_url"])}
        except ValueError:
            pass
    chosen=None
    try:
        search=fetch({"action":"wbsearchentities","search":name,"language":"en",
                      "type":"item","limit":7}).get("search",[])
        candidates=[r for r in search if normalize(r.get("label"))==normalize(name)
                    and "box" in r.get("description","").casefold()]
        if len(candidates)==1:
            qid=candidates[0]["id"]
            entity=fetch({"action":"wbgetentities","ids":qid,"props":"claims"})
            chosen=choose_photo(name,search,entity.get("entities",{}))
    except (requests.RequestException,ValueError,KeyError,TypeError):
        # Network outages are not cached as an absence of image.
        return {"url":None,"source":None}
    with connect() as c:
        c.execute("""INSERT INTO hub_verified_images
          (fighter_id,image_url,source_url,checked_at) VALUES(?,?,?,?)
          ON CONFLICT(fighter_id) DO UPDATE SET
            image_url=excluded.image_url,source_url=excluded.source_url,
            checked_at=excluded.checked_at""",
            (fighter_id,chosen["url"] if chosen else None,
             chosen["source"] if chosen else None,
             datetime.now(timezone.utc).isoformat()))
    return chosen or {"url":None,"source":None}
