"""Smoke tests for bundled Open Boxing historical data."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
import boxing_feed as feed


class OpenBoxingArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_app_db = app.DB_PATH
        self.original_feed_db = feed.DB
        path = Path(self.tmp.name) / "fightbase.db"
        app.DB_PATH = path
        feed.DB = path
        app.init_db()
        feed.init_feed()
        self.client = app.app.test_client()

    def tearDown(self):
        app.DB_PATH = self.original_app_db
        feed.DB = self.original_feed_db
        self.tmp.cleanup()

    def test_imported_real_fights_and_fighters(self):
        self.assertGreaterEqual(feed.archive_count(), 6000)
        self.assertGreaterEqual(feed.fighters_count(), 1500)
        self.assertTrue(feed.results())
        self.assertTrue(all(row["status"] == "FINISHED" for row in feed.results()))

    def test_bundle_is_idempotent(self):
        before = feed.archive_count()
        feed.init_feed()
        self.assertEqual(feed.archive_count(), before)

    def test_boxing_history_shows_real_names_and_not_future_dates(self):
        self.assertEqual(self.client.get("/?tab=results").status_code, 200)
        result = self.client.get("/")
        self.assertEqual(result.status_code, 200)
        self.assertIn(b"HISTORISCHE ERGEBNISSE", result.data)
        # Rumble in the Jungle is included in the historical bout archive.
        ali = feed.rows("""SELECT * FROM hub_fights
            WHERE a_name='George Foreman' AND b_name='Muhammad Ali'
            AND fight_date LIKE '1974%'""")
        self.assertTrue(ali)
        self.assertEqual(ali[0]["winner_id"], ali[0]["b_id"])
        self.assertEqual(self.client.get("/kampf/" + ali[0]["id"]).status_code, 200)

    def test_no_made_up_boxer_career_record(self):
        row = feed.one("SELECT * FROM hub_fighters WHERE name='Muhammad Ali' LIMIT 1")
        self.assertIsNotNone(row)
        self.assertIsNone(row["wins"])
        self.assertIsNone(row["losses"])
        self.assertEqual(self.client.get("/boxer/" + row["id"]).status_code, 200)

    def test_old_manual_comparison_untouched(self):
        self.assertEqual(self.client.get("/vergleich").status_code, 200)
        self.assertEqual(len(feed.rows("SELECT * FROM history")), 0)


if __name__ == "__main__":
    unittest.main()
