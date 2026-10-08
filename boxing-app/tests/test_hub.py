import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app
import boxing_feed as feed


class BoxingHubTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db = app.DB_PATH
        self.old_feed_db = feed.DB
        path = Path(self.temp.name) / "test.db"
        app.DB_PATH = path
        feed.DB = path
        app.init_db()
        feed.init_feed()
        self.client = app.app.test_client()
        self.env = patch.dict(os.environ, {"BOXING_API_KEY": ""})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        app.DB_PATH = self.old_db
        feed.DB = self.old_feed_db
        self.temp.cleanup()

    def test_empty_hub_and_old_comparison(self):
        for route in ("/", "/?tab=results", "/?tab=fighters", "/?tab=events",
                      "/?tab=rankings", "/vergleich"):
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(response.status_code, 200)

    def test_fight_details_profile_and_saving_prediction(self):
        for identifier, name, wins, losses in [
            ("f1", "Demo Red Boxer", 20, 2),
            ("f2", "Demo Blue Boxer", 15, 3)
        ]:
            feed.save_fighter({
                "id": identifier, "name": name, "age": 28,
                "stats": {"wins": wins, "losses": losses, "draws": 0,
                          "ko_wins": 10},
                "nationality": "Test"
            })
        feed.save_fights([{
            "id": "test-bout", "title": "Demo Red vs Demo Blue",
            "date": "2026-12-25T20:00:00", "status": "NOT_STARTED",
            "fighters": {
                "fighter_1": {"fighter_id": "f1", "full_name": "Demo Red Boxer"},
                "fighter_2": {"fighter_id": "f2", "full_name": "Demo Blue Boxer"}
            },
            "event": {"id": "test-event", "title": "Sample"},
            "division": {"name": "Heavyweight"}
        }])
        self.assertEqual(self.client.get("/kampf/test-bout").status_code, 200)
        self.assertEqual(self.client.get("/boxer/f1").status_code, 200)
        response = self.client.post("/kampf/test-bout/analysieren")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/vergleich?load=", response.location)
        self.assertEqual(len(feed.rows("SELECT * FROM history")), 1)
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_only_one_cached_photo_is_returned(self):
        feed.save_fighter({"id": "photo-id", "name": "Demo Boxer"})
        with feed.connect() as db:
            db.execute("INSERT INTO hub_images VALUES (?,?,?,?)", (
                "photo-id", "https://example.org/photo.jpg",
                "https://example.org/source", feed.utcnow()))
        response = self.client.get("/api/foto/photo-id")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["url"], "https://example.org/photo.jpg")


if __name__ == "__main__":
    unittest.main()
