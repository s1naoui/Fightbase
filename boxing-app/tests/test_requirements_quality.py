import unittest
import tempfile
from pathlib import Path

import app
import boxing_feed as feed
from prediction import calculate_three_way


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.old_app = app.DB_PATH
        self.old_feed = feed.DB
        db=Path(self.folder.name)/"test.db"
        app.DB_PATH=db
        feed.DB=db
        app.init_db()
        feed.init_feed()
        self.client=app.app.test_client()

    def tearDown(self):
        app.DB_PATH=self.old_app
        feed.DB=self.old_feed
        self.folder.cleanup()

    def test_upcoming_real_pairs_and_source(self):
        bouts=feed.upcoming()
        self.assertGreaterEqual(len(bouts),3)
        names=[(b["a_name"],b["b_name"]) for b in bouts]
        self.assertIn(("Daniel Dubois","Fabio Wardley"),names)
        for bout in bouts:
            self.assertTrue(bout["a_name"])
            self.assertTrue(bout["b_name"])
            self.assertIsNotNone(feed.one(
                "SELECT source_url FROM hub_sources WHERE entity_id=?",(bout["id"],)))
            self.assertEqual(self.client.get("/kampf/"+bout["id"]).status_code,200)

    def test_reviewed_records_are_not_made_up_for_all(self):
        row=feed.one("SELECT * FROM hub_fighters WHERE id='reviewed-daniel-dubois'")
        self.assertEqual((row["wins"],row["losses"],row["draws"],row["ko_wins"]),
                         (23,3,0,22))
        historical=feed.one("SELECT * FROM hub_fighters WHERE id='ob-c-252'")
        self.assertIsNone(historical["wins"])

    def test_three_outcomes_sum_to_100(self):
        a={"name":"A","wins":23,"losses":3,"age":29}
        b={"name":"B","wins":20,"losses":1,"age":None}
        result=calculate_three_way(a,b)
        self.assertAlmostEqual(
            result["probability_a"]+result["probability_draw"]+result["probability_b"],
            100.0)
        self.assertIn(b"Unentschieden",self.client.get(
            "/kampf/"+next(b["id"] for b in feed.upcoming()
                            if b["a_name"]=="Daniel Dubois")).data)

if __name__ == "__main__":
    unittest.main()
