"""Admin authentication, sourced records and fixture creation."""
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app
import boxing_feed as feed
import fightbase_admin as admin


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=app.DB_PATH
        self.old_feed=feed.DB
        db=Path(self.tmp.name)/"test.db"
        app.DB_PATH=feed.DB=db
        self.env=patch.dict(os.environ,{
            "FIGHTBASE_ADMIN_PASSWORD":"SuperSafeTestPassword!27",
            "FIGHTBASE_SECRET_KEY":"a"*48
        })
        self.env.start()
        app.init_db()
        feed.init_feed()
        admin.ensure_tables()
        self.client=app.app.test_client()
        self.fid="reviewed-tyson-fury"

    def tearDown(self):
        self.env.stop()
        app.DB_PATH=self.old_db
        feed.DB=self.old_feed
        self.tmp.cleanup()

    def csrf(self):
        with self.client.session_transaction() as s:
            return s["fightbase_csrf"]

    def login(self):
        self.client.get("/admin/login")
        response=self.client.post("/admin/login",data={
            "csrf_token":self.csrf(),"password":"SuperSafeTestPassword!27"})
        self.assertEqual(response.status_code,302)
        return response

    def test_admin_requires_login_and_csrf(self):
        self.assertEqual(self.client.get("/admin").status_code,302)
        self.assertEqual(self.client.post("/admin/boxer/"+self.fid+"/bilanz").status_code,403)
        self.login()
        self.assertEqual(self.client.get("/admin").status_code,200)
        response=self.client.post("/admin/boxer/"+self.fid+"/bilanz",
                                  data={"csrf_token":"wrong"})
        self.assertEqual(response.status_code,400)

    def test_sourced_records_survive_seed_restart(self):
        self.login()
        response=self.client.post("/admin/boxer/"+self.fid+"/bilanz",data={
             "csrf_token":self.csrf(),"wins":"37","losses":"2",
             "draws":"1","ko_wins":"26","source_url":"https://example.com/boxing-record"})
        self.assertEqual(response.status_code,302)
        before=feed.one("SELECT * FROM hub_fighters WHERE id=?",(self.fid,))
        self.assertEqual((before["wins"],before["losses"],before["draws"],before["ko_wins"]),
                         (37,2,1,26))
        feed.init_feed()
        persisted=feed.one("SELECT * FROM hub_fighters WHERE id=?",(self.fid,))
        self.assertEqual(persisted["wins"],37)
        self.assertIn(b"Bilanz-Quelle",self.client.get("/boxer/"+self.fid).data)
        bad=self.client.post("/admin/boxer/"+self.fid+"/bilanz",data={
             "csrf_token":self.csrf(),"wins":"1","losses":"2",
             "draws":"1","ko_wins":"4","source_url":"javascript:alert(1)"})
        self.assertEqual(bad.status_code,302)
        self.assertEqual(feed.one("SELECT wins FROM hub_fighters WHERE id=?",(self.fid,))["wins"],37)
        reset=self.client.post("/admin/boxer/"+self.fid+"/bilanz/zuruecksetzen",
                    data={"csrf_token":self.csrf()})
        self.assertEqual(reset.status_code,302)
        record=feed.one("SELECT wins,losses,ko_wins FROM hub_fighters WHERE id=?",(self.fid,))
        self.assertEqual((record["wins"],record["losses"],record["ko_wins"]),(36,2,25))
        self.assertIsNone(feed.one("SELECT * FROM hub_admin_records WHERE fighter_id=?",
                                    (self.fid,)))

    def test_knockout_stats_affect_three_way_rating(self):
        from prediction import calculate_three_way
        a={"name":"A","age":28,"wins":24,"losses":1,"draws":0,"ko_wins":21}
        b={"name":"B","age":28,"wins":24,"losses":1,"draws":0,"ko_wins":3}
        result=calculate_three_way(a,b)
        self.assertGreater(result["score_a"],result["score_b"])
        self.assertGreater(result["probability_a"],result["probability_b"])
        self.assertAlmostEqual(result["probability_a"]+
            result["probability_b"]+result["probability_draw"],100.0)

    def test_add_sourced_fight_and_remove_it(self):
        self.login()
        day=(date.today()+timedelta(days=30)).isoformat()
        response=self.client.post("/admin/kampf",data={
             "csrf_token":self.csrf(),"boxer_a":"Fighter Test A",
             "boxer_b":"Fighter Test B","date":day,"time":"",
             "venue":"Demo Arena","location":"Wien, Österreich",
             "division":"Heavyweight","event":"Test Fight Night",
             "source_url":"https://example.com/verified-event"})
        self.assertEqual(response.status_code,302)
        entry=feed.one("SELECT * FROM hub_fights WHERE a_name='Fighter Test A'")
        self.assertIsNotNone(entry)
        self.assertIn(entry["id"],[x["id"] for x in feed.upcoming()])
        self.assertIsNotNone(feed.one("SELECT * FROM hub_events WHERE id=?",(entry["event_id"],)))
        deleted=self.client.post("/admin/kampf/"+entry["id"]+"/loeschen",
                        data={"csrf_token":self.csrf()})
        self.assertEqual(deleted.status_code,302)
        self.assertIsNone(feed.one("SELECT * FROM hub_fights WHERE id=?",(entry["id"],)))


if __name__=="__main__":
    unittest.main()
