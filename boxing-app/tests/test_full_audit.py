"""Audit tests for sourced fight data, portraits, UI pages, and response latency."""
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import boxing_feed as feed
from prediction import calculate_three_way
import identity_photos


class FightbaseAudit(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.app_db=app.DB_PATH
        self.feed_db=feed.DB
        db=Path(self.folder.name)/"audit.sqlite3"
        app.DB_PATH=feed.DB=db
        app.init_db()
        feed.init_feed()
        self.client=app.app.test_client()

    def tearDown(self):
        app.DB_PATH=self.app_db
        feed.DB=self.feed_db
        self.folder.cleanup()

    def test_event_start_times_and_sources(self):
        from verified_fights import fighter_key
        schofield=feed.one("SELECT * FROM hub_fights WHERE a_id=? AND b_id=?",
             (fighter_key("Floyd Schofield"),fighter_key("Lucas Bahdi")))
        self.assertIsNotNone(schofield)
        self.assertEqual(schofield["fight_date"],"2026-10-10T15:15:00-05:00")
        self.assertIsNotNone(feed.one(
             "SELECT * FROM hub_events WHERE id=?",(schofield["event_id"],)))
        self.assertIn(b"15:15 Uhr",self.client.get("/kampf/"+schofield["id"]).data)
        dubois=feed.one("SELECT * FROM hub_fights WHERE a_id=?",
             (fighter_key("Daniel Dubois"),))
        self.assertIn(b"Uhrzeit nicht best",self.client.get("/kampf/"+dubois["id"]).data)

    def test_all_reviewed_pairings_have_records_and_sources(self):
        from verified_fights import SCHEDULE,RECORDS,fighter_key
        self.assertEqual(len(SCHEDULE),8)
        self.assertGreaterEqual(len(RECORDS),16)
        for start,a,b,*other in SCHEDULE:
            for name in (a,b):
                person=feed.one("SELECT * FROM hub_fighters WHERE id=?",
                                (fighter_key(name),))
                self.assertIsNotNone(person,name)
                self.assertIsNotNone(person["wins"],name)
                self.assertIsNotNone(person["losses"],name)
                self.assertIsNotNone(person["ko_wins"],name)
                self.assertIsNotNone(feed.one(
                    "SELECT source_url FROM hub_sources WHERE entity_id=?",
                    (fighter_key(name),)))

    def test_past_scheduled_bout_does_not_get_a_forecast(self):
        from verified_fights import fighter_key
        name=fighter_key("Daniel Dubois")
        bout=feed.one("SELECT * FROM hub_fights WHERE a_id=?",(name,))
        with feed.connect() as db:
            db.execute("UPDATE hub_fights SET fight_date='2021-01-01' WHERE id=?",
                       (bout["id"],))
        page=self.client.get("/kampf/"+bout["id"])
        self.assertEqual(page.status_code,200)
        self.assertNotIn(b'three-prob-bar',page.data)

    def test_known_birthdates_and_records(self):
        for name,expected in (
            ("reviewed-floyd-schofield",24),
            ("reviewed-lucas-bahdi",32),
            ("reviewed-fabio-wardley",31),
        ):
            boxer=feed.one("SELECT * FROM hub_fighters WHERE id=?",(name,))
            self.assertEqual(boxer["age"],expected)

    def test_historical_winner_is_visible(self):
        ali=feed.one("""SELECT * FROM hub_fights WHERE a_name='George Foreman'
                 AND b_name='Muhammad Ali' AND fight_date LIKE '1974%'""")
        self.assertIsNotNone(ali)
        page=self.client.get("/kampf/"+ali["id"])
        self.assertEqual(page.status_code,200)
        self.assertIn(b"Sieger",page.data)
        self.assertIn(b"Muhammad Ali",page.data)

    def test_three_outcomes_and_charts(self):
        a={"name":"A","age":31,"wins":20,"losses":1}
        b={"name":"B","age":27,"wins":18,"losses":0}
        result=calculate_three_way(a,b)
        self.assertAlmostEqual(result["probability_a"]+
             result["probability_draw"]+result["probability_b"],100.0)
        from verified_fights import fighter_key
        match=feed.one("SELECT * FROM hub_fights WHERE a_id=?",
                       (fighter_key("Daniel Dubois"),))
        content=self.client.get("/kampf/"+match["id"]).data
        self.assertIn(b"three-prob-bar",content)
        self.assertIn(b"Unentschieden",content)

    def test_photo_api_is_nonblocking_and_no_random_legacy_photo(self):
        feed.save_fighter({"id":"audit-test","name":"Demo Boxer"})
        with patch("portal.feed.photo",side_effect=RuntimeError("Should not be used")):
            with patch("identity_photos.quick_verified_photo",
                       return_value={"url":None,"source":None,"pending":True}):
                start=time.perf_counter()
                response=self.client.get("/api/foto/audit-test")
                elapsed=time.perf_counter()-start
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.json["pending"])
        self.assertLess(elapsed,3.0)
        with patch("identity_photos.quick_verified_photo",
                   return_value={"url":None,"source":None,"pending":True}):
            response=self.client.get("/vergleich/verifiziertes-foto?name=Tyson%20Fury")
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.json["pending"])

    def test_routes_and_local_response_speed(self):
        for url in ["/","/?tab=results","/?tab=fighters","/?tab=events",
                    "/?tab=organizations","/?tab=rankings","/vergleich"]:
            self.client.get(url)
            start=time.perf_counter()
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertLess(time.perf_counter()-start,3.0,url)


if __name__=="__main__":
    unittest.main()
