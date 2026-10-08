"""Reviewed facts from dated public boxing sources; not a live API.

The timestamp below documents when the snapshot was verified. Values must
not be silently treated as current after subsequent fights.
"""
from datetime import date

AS_OF = "2026-10-08"
RECORDS = [
 ("Osleys Iglesias",15,0,0,14,None,"Cuba","Super Middleweight","https://www.ringmagazine.com/news/VxAqTbFGKirVrSQgmiY6K"),
 ("Oliver Zaren",19,0,1,8,None,"Denmark","Super Middleweight","https://www.ringmagazine.com/news/VxAqTbFGKirVrSQgmiY6K"),
 ("Sebastian Fundora",24,1,1,16,None,"United States","Super Welterweight","https://origin.premierboxingchampions.com/sebastian-fundora"),
 ("Ermal Hadribeaj",22,0,1,8,"1993-10-11","United States","Super Welterweight","https://www.ringmagazine.com/fighters/ermal-hadribeaj-70SNbkWZvHnLYdyr7ZQktd"),
 ("Dalton Smith",19,0,0,14,None,"United Kingdom","Super Lightweight","https://wbcboxing.com/en/where-to-watch-smith-vs-puello/"),
 ("Alberto Puello",25,1,0,11,"1994-07-22","Dominican Republic","Super Lightweight","https://wbcboxing.com/en/where-to-watch-smith-vs-puello/"),
 ("Emanuel Navarrete",40,2,1,33,None,"Mexico","Super Featherweight","https://champinon.info/de/schedule/navarrete-vs-foster/"),
 ("O'Shaquie Foster",25,3,0,12,"1993-09-17","United States","Super Featherweight","https://www.boxingschedule.info/fighters/oshaquie-foster"),
 ("Elif Nur Turhan",14,0,0,8,None,"Türkiye","Lightweight","https://champinon.info/de/boxing/elif-nur-turhan/"),
 ("Alycia Baumgardner",18,1,0,7,None,"United States","Lightweight","https://www.ringmagazine.com/events/turhan-vs-baumgardner-6X6oyTmwE55wWOWk5nU5f4"),
 ("Floyd Schofield",19,0,0,13,"2002-08-27","USA","Lightweight","https://fightnights.com/boxers/Floyd-Schofield-record-5856"),
 ("Lucas Bahdi",20,0,0,15,"1994-01-27","Canada","Lightweight","https://www.fightnights.com/boxers/Lucas-Bahdi-record-6090"),
 ("Daniel Dubois",23,3,0,22,"1997-09-06","United Kingdom","Heavyweight","https://fightnights.com/boxers/Daniel-Dubois-record-5280"),
 ("Fabio Wardley",20,1,1,19,"1994-12-18","United Kingdom","Heavyweight","https://fightnights.com/boxers/Fabio-Wardley-record-5816"),
 ("Tyson Fury",36,2,1,25,"1988-06-01","United Kingdom","Heavyweight","https://www.fightnights.com/boxers/Tyson-Fury-record-1734"),
 ("Anthony Joshua",30,4,0,27,"1989-10-15","United Kingdom","Heavyweight","https://fightnights.com/boxers/Anthony-Joshua-record-3699"),
]
# Time is the start of the event in local time, NOT fighter ring walk.
SCHEDULE = [
 ("2026-10-08","Osleys Iglesias","Oliver Zaren",
  "Capitole de Québec","Québec City, Canada","Super Middleweight","IBF",
  "https://fightnights.com/upcoming-boxing-schedule"),
 ("2026-10-17T14:00:00-07:00","Sebastian Fundora","Ermal Hadribeaj",
  "The Cosmopolitan","Las Vegas, USA","Super Welterweight","WBC",
  "https://cosmopolitanlasvegas.mgmresorts.com/en/entertainment/pbc-boxing.html"),
 ("2026-10-24T16:00:00+01:00","Dalton Smith","Alberto Puello",
  "Utilita Arena","Sheffield, United Kingdom","Super Lightweight","WBC",
  "https://www.ticketmaster.co.uk/matchroom-boxing-uk-tickets/artist/5363334"),
 ("2026-10-24","Emanuel Navarrete","O'Shaquie Foster",
  "Frost Bank Center","San Antonio, USA","Super Featherweight","",
  "https://fightnights.com/upcoming-boxing-schedule"),
 ("2026-11-08","Elif Nur Turhan","Alycia Baumgardner",
  "College Park Center","Arlington, USA","Lightweight","IBF",
  "https://fightnights.com/upcoming-boxing-schedule"),
 ("2026-10-10T15:15:00-05:00","Floyd Schofield","Lucas Bahdi",
  "Wintrust Arena","Chicago, USA","Lightweight","WBA",
  "https://www.wintrustarena.com/events/detail/golden-boy"),
 ("2026-10-17","Daniel Dubois","Fabio Wardley",
  "The O2","London, United Kingdom","Heavyweight","WBO",
  "https://www.fightnights.com/Daniel-Dubois-vs-Fabio-Wardley-II-WBO-World-Heavyweight-Title-3883"),
 ("2026-12-11T17:00:00+00:00","Tyson Fury","Anthony Joshua",
  "Principality Stadium","Cardiff, United Kingdom","Heavyweight","",
  "https://www.principalitystadium.wales/event/tyson-fury-v-anthony-joshua/"),
]


def fighter_key(name):
    import re
    return "reviewed-" + re.sub(r"[^a-z0-9]+","-",name.casefold()).strip("-")


def seed_verified():
    """Upsert a dated, sourced record snapshot; do not infer incomplete career histories."""
    from boxing_feed import connect
    with connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS hub_sources (
          entity_id TEXT PRIMARY KEY, source_url TEXT NOT NULL,
          reviewed_on TEXT NOT NULL, source_kind TEXT NOT NULL,
          time_note TEXT DEFAULT '')""")
        for name,w,l,d,ko,born,nationality,division,url in RECORDS:
            age = None
            if born:
                bdate=date.fromisoformat(born)
                today=date.today()
                age=today.year-bdate.year - (
                    (today.month,today.day)<(bdate.month,bdate.day))
            fid=fighter_key(name)
            db.execute("""INSERT INTO hub_fighters
              (id,name,age,wins,losses,draws,ko_wins,nationality,division,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,age=excluded.age,
                wins=excluded.wins,losses=excluded.losses,
                draws=excluded.draws,ko_wins=excluded.ko_wins,
                nationality=excluded.nationality,division=excluded.division,
                updated_at=excluded.updated_at""",
                (fid,name,age,w,l,d,ko,nationality,division,AS_OF))
            db.execute("""INSERT INTO hub_sources (entity_id,source_url,reviewed_on,source_kind)
              VALUES (?,?,?,'reviewed-profile')
              ON CONFLICT(entity_id) DO UPDATE SET
                source_url=excluded.source_url,reviewed_on=excluded.reviewed_on""",
                (fid,url,AS_OF))
        for start,a,b,venue,city,division,belt,url in SCHEDULE:
            # Participants without reliable career records still get searchable profiles.
            for boxer_name in (a,b):
                db.execute("""INSERT INTO hub_fighters(id,name,division,updated_at)
                VALUES (?,?,?,?) ON CONFLICT(id) DO NOTHING""",
                    (fighter_key(boxer_name),boxer_name,division,AS_OF))
            fid="scheduled-"+start[:10]+"-"+fighter_key(a)+"-"+fighter_key(b)
            event_id="event-"+fid
            db.execute("""INSERT INTO hub_fights
              (id,fight_date,title,status,a_id,b_id,a_name,b_name,
               division,event_id,event_title,venue,location,updated_at)
              VALUES(?,?,?,'NOT_STARTED',?,?,?,?,?,?,?,?,?,?)
              ON CONFLICT(id) DO UPDATE SET
               fight_date=excluded.fight_date,title=excluded.title,
               a_id=excluded.a_id,b_id=excluded.b_id,
               a_name=excluded.a_name,b_name=excluded.b_name,
               division=excluded.division,venue=excluded.venue,
               location=excluded.location,event_title=excluded.event_title,
               event_id=excluded.event_id""",
              (fid,start,a+" vs "+b,fighter_key(a),fighter_key(b),a,b,division,
               event_id,belt+" title fight" if belt else "Boxevent",
               venue,city,AS_OF))
            db.execute("""INSERT INTO hub_events(id,title,event_date,venue,location,updated_at)
                VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                event_date=excluded.event_date,venue=excluded.venue,
                location=excluded.location,updated_at=excluded.updated_at""",
                (event_id,a+" vs "+b,start[:10],venue,city,AS_OF))
            db.execute("""INSERT INTO hub_sources
               (entity_id,source_url,reviewed_on,source_kind,time_note)
               VALUES(?,?,?,'reviewed-schedule',?)
               ON CONFLICT(entity_id) DO UPDATE SET
                source_url=excluded.source_url,reviewed_on=excluded.reviewed_on,
                time_note=excluded.time_note""",
               (fid,url,AS_OF,
                "Veranstaltungsbeginn / erster Kampf (nicht Ringwalk)" if "T" in start
                else "Uhrzeit bisher nicht zuverlässig bestätigt"))
