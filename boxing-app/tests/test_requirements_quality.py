import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

import app
import boxing_feed as feed
from identity_photos import choose_photo
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
            "/kampf/"+feed.upcoming()[0]["id"]).data)

    def test_photo_rejects_mismatched_or_ambiguous_entity(self):
        sample={"P106":[{"mainsnak":{"datavalue":{"value":{"id":"Q11338576"}}}}],
                "P18":[{"mainsnak":{"datavalue":{"value":"Test.jpg"}}}]}
        search=[{"id":"Q123","label":"Daniel Dubois",
                 "description":"British professional boxer"}]
        good=choose_photo("Daniel Dubois",search,{"Q123":{"claims":sample}})
        self.assertIn("Test.jpg",good["url"])
        self.assertIsNone(choose_photo("Anthony Joshua",search,
                                      {"Q123":{"claims":sample}}))
        self.assertIsNone(choose_photo("Daniel Dubois",search,
                                      {"Q123":{"claims":{"P18":sample["P18"]}}}))
        self.assertIsNone(choose_photo("Daniel Dubois",search+search,
                                      {"Q123":{"claims":sample}}))


if __name__ == "__main__":
    unittest.main()
