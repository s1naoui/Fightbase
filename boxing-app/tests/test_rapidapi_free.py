"""Offline-only tests for optional monthly-capped Boxing Data API integration."""
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app
import boxing_feed as feed
import boxing_rapidapi as rapid


class Response:
    def __init__(self,data,status=200):
        self.status_code=status
        self.data=data

    def json(self):
        return {"error":{},"data":self.data}


class RapidApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.app_path=app.DB_PATH
        self.feed_path=feed.DB
        app.DB_PATH=feed.DB=Path(self.tmp.name)/"local.sqlite3"
        self.env=patch.dict(os.environ,{"BOXING_API_KEY":"TEST_SECRET_NEVER_COMMIT",
            "BOXING_API_AUTO_SYNC":"true"})
        self.env.start()
        app.init_db()
        feed.init_feed()
        self.client=app.app.test_client()

    def tearDown(self):
        self.env.stop()
        app.DB_PATH=self.app_path
        feed.DB=self.feed_path
        self.tmp.cleanup()

    def test_no_request_without_key_and_invalid_endpoint(self):
        with patch.dict(os.environ,{"BOXING_API_KEY":""}):
            with patch("boxing_rapidapi.requests.get") as transport:
                with self.assertRaises(rapid.ApiAccessError):
                    rapid.call("fighters")
                transport.assert_not_called()
        with self.assertRaises(ValueError):
            rapid.call("https://evil.example/api")

    def test_one_connection_test_updates_cached_boxer_and_hides_key(self):
        boxer={"id":"remote-fury-1","name":"Tyson Fury","age":38,
               "nationality":"United Kingdom",
               "stats":{"wins":36,"losses":2,"draws":1,"ko_wins":25},
               "division":{"name":"Heavyweight"}}
        with patch("boxing_rapidapi.requests.get",return_value=Response([boxer])) as req:
            outcome=rapid.verify()
        self.assertEqual(outcome["profiles"],1)
        self.assertEqual(req.call_count,1)
        self.assertEqual(rapid.usage()["used"],1)
        self.assertEqual(req.call_args.kwargs["headers"]["X-RapidAPI-Key"],
                         "TEST_SECRET_NEVER_COMMIT")
        fighter=feed.one("SELECT * FROM hub_fighters WHERE id='reviewed-tyson-fury'")
        self.assertEqual((fighter["wins"],fighter["losses"],fighter["ko_wins"]),
                         (36,2,25))
        calls=feed.rows("SELECT * FROM rapid_api_calls")
        self.assertNotIn("TEST_SECRET_NEVER_COMMIT",str([dict(c) for c in calls]))
        feed.init_feed()
        restored=feed.one("SELECT * FROM hub_fighters WHERE id='reviewed-tyson-fury'")
        self.assertEqual(restored["wins"],36)

    def test_provider_denied_route_not_called_again_and_cache_kept(self):
        denied=Response([],status=403)
        with patch("boxing_rapidapi.requests.get",return_value=denied) as req:
            with self.assertRaisesRegex(rapid.ApiAccessError,"Gratis"):
                rapid.call("schedule",{"days":30})
            with self.assertRaisesRegex(rapid.ApiAccessError,"gesperrt"):
                rapid.call("schedule",{"days":30})
        self.assertEqual(req.call_count,1)
        self.assertEqual(rapid.usage()["used"],1)
        self.assertGreater(feed.archive_count(),6000)

    def test_monthly_budget_caps_all_attempts(self):
        with feed.connect() as db:
            for _ in range(rapid.MONTHLY_CAP):
                db.execute("""INSERT INTO rapid_api_calls(month,endpoint,created_at)
                   VALUES(?,?,?)""",(rapid.month(),"test",feed.utcnow()))
        with patch("boxing_rapidapi.requests.get") as transport:
            with self.assertRaisesRegex(rapid.ApiAccessError,"Sicherheitslimit"):
                rapid.call("fighters")
            transport.assert_not_called()
        self.assertEqual(rapid.usage()["remaining"],0)

    def test_successful_import_future_and_recent_with_links(self):
        future=(date.today()+timedelta(days=8)).isoformat()+"T18:00:00"
        past=(date.today()-timedelta(days=8)).isoformat()+"T18:00:00"
        def bout(identifier, day,status):
            return {
                "id":identifier,"date":day,"status":status,
                "title":"Tyson Fury vs Anthony Joshua",
                "venue":"Test Arena","location":"Test City",
                "event":{"id":"event-"+identifier,"title":"Test Event","date":day},
                "division":{"name":"Heavyweight"},
                "fighters":{
                    "fighter_1":{"fighter_id":"remote-fury","full_name":"Tyson Fury",
                                 "winner":status=="FINISHED"},
                    "fighter_2":{"fighter_id":"remote-joshua","full_name":"Anthony Joshua",
                                 "winner":False}},
                "results":{"outcome":"KO","round":"5"} if status=="FINISHED" else None,
            }
        fighter={"id":"remote-fury","name":"Tyson Fury","age":38,
                 "stats":{"wins":36,"losses":2,"draws":1,"ko_wins":25},
                 "division":{"name":"Heavyweight"}}
        def respond(url,params=None,headers=None,timeout=None):
            if url.endswith("/fights/schedule"):
                return Response([bout("new-2026",future,"NOT_STARTED")])
            if url.endswith("/fights/"):
                return Response([bout("old-2026",past,"FINISHED")])
            if params and params.get("name"):
                return Response([fighter])
            return Response([fighter])
        with patch("boxing_rapidapi.requests.get",side_effect=respond) as req:
            summary=rapid.synchronize(force=True)
        self.assertEqual(summary["fights"],2)
        self.assertGreaterEqual(summary["profiles"],1)
        self.assertLessEqual(summary["requested"],5)
        future_fight=feed.one("SELECT * FROM hub_fights WHERE id='rapid-new-2026'")
        old=feed.one("SELECT * FROM hub_fights WHERE id='rapid-old-2026'")
        self.assertEqual(future_fight["a_id"],"reviewed-tyson-fury")
        self.assertEqual(old["outcome"],"KO")
        self.assertEqual(old["winner_id"],"reviewed-tyson-fury")
        self.assertIsNotNone(feed.one("SELECT * FROM hub_events WHERE id=?",
                         (future_fight["event_id"],)))
        self.assertIsNotNone(feed.one("SELECT * FROM hub_sources WHERE entity_id=?",
                         (future_fight["id"],)))
        self.assertEqual(self.client.get("/kampf/rapid-new-2026").status_code,200)
        self.assertEqual(self.client.get("/kampf/rapid-old-2026").status_code,200)
        with patch("boxing_rapidapi.requests.get") as transport:
            summary2=rapid.synchronize(force=False)
            self.assertEqual(summary2["requested"],0)
            transport.assert_not_called()

    def test_manual_records_survive_rapid_import(self):
        with feed.connect() as db:
            db.execute("""INSERT INTO hub_admin_records
                 (fighter_id,wins,losses,draws,ko_wins,source_url,updated_at)
                 VALUES ('reviewed-tyson-fury',50,1,0,40,'https://example.org/source',?)""",
                 (feed.utcnow(),))
        with patch("boxing_rapidapi.requests.get",return_value=Response([{
            "id":"remote-fury","name":"Tyson Fury",
            "stats":{"wins":35,"losses":2,"draws":1,"ko_wins":25}}])):
            rapid.verify()
        fighter=feed.one("SELECT * FROM hub_fighters WHERE id='reviewed-tyson-fury'")
        self.assertEqual((fighter["wins"],fighter["ko_wins"]),(50,40))
        feed.init_feed()
        fighter=feed.one("SELECT * FROM hub_fighters WHERE id='reviewed-tyson-fury'")
        self.assertEqual((fighter["wins"],fighter["ko_wins"]),(50,40))

    def test_admin_connection_screen_does_not_spend_credit(self):
        page=self.client.get("/admin/login")
        self.assertEqual(page.status_code,200)
        with patch("boxing_rapidapi.requests.get") as transport:
            self.client.get("/")
            self.assertEqual(rapid.usage()["used"],0)
            transport.assert_not_called()


if __name__=="__main__":
    unittest.main()
