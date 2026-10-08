"""Narrow, sourced corrections to demonstrably wrong dates in provider data.

Apply after reading cached provider records and after new imports. Never
guess missing matches and never modify manually entered or Open Boxing fights.
"""
from __future__ import annotations
from datetime import date


CORRECTIONS = (
    {
        "boxer_a": "Omari Jones",
        "boxer_b": "Alan Sanchez",
        "reported_date": "2026-10-03",
        "verified_date": "2026-10-02",
        "source": "https://www.cariberoyale.com/boxing",
        "details": "Der Veranstaltungsort bestätigt Freitag, den 02.10.2026; "
                   "der importierte API-Datensatz nennt irrtümlich den 03.10.2026.",
    },
)


def apply():
    """Fix only explicitly matched result IDs/names/date, keeping local data."""
    import boxing_feed as feed

    fixed = 0
    with feed.connect() as db:
        for item in CORRECTIONS:
            bouts = db.execute(
                """SELECT id,event_id FROM hub_fights WHERE id LIKE 'rapid-%'
                   AND status='FINISHED' AND substr(fight_date,1,10)=?
                   AND a_name=? COLLATE NOCASE AND b_name=? COLLATE NOCASE""",
                (item["reported_date"],item["boxer_a"],item["boxer_b"])
            ).fetchall()
            for bout in bouts:
                db.execute("""UPDATE hub_fights SET fight_date=?,updated_at=?
                    WHERE id=?""",
                    (item["verified_date"],feed.utcnow(),bout["id"]))
                db.execute("""INSERT INTO hub_sources(
                    entity_id,source_url,reviewed_on,source_kind,time_note)
                    VALUES(?,?,?,'reviewed-api-date-correction',?)
                    ON CONFLICT(entity_id) DO UPDATE SET
                    source_url=excluded.source_url,
                    reviewed_on=excluded.reviewed_on,
                    source_kind=excluded.source_kind,
                    time_note=excluded.time_note""",
                    (bout["id"],item["source"],date.today().isoformat(),
                     item["details"]))
                if bout["event_id"] and bout["event_id"].startswith("rapid-event-"):
                    other = db.execute(
                        "SELECT COUNT(*) AS n FROM hub_fights WHERE event_id=? AND id<>?",
                        (bout["event_id"],bout["id"])
                    ).fetchone()["n"]
                    if other == 0:
                        db.execute("""UPDATE hub_events SET event_date=? WHERE id=?
                            AND substr(event_date,1,10)=?""",
                            (item["verified_date"],bout["event_id"],
                             item["reported_date"]))
                fixed += 1
    return fixed
