"""Regression tests for automated, safe admin ZIP boxer-photo import."""
import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import app
import boxing_feed as feed
import fightbase_admin as admin


def make_png(color=(50, 100, 150)):
    output = io.BytesIO()
    Image.new("RGB", (420, 550), color).save(output, "PNG")
    return output.getvalue()


def make_zip(entries):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, contents in entries:
            archive.writestr(filename, contents)
    stream.seek(0)
    return stream


class BulkPhotoImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_app_db = app.DB_PATH
        self.old_feed_db = feed.DB
        self.old_uploads = admin.UPLOADS
        testdb = Path(self.tmp.name) / "boxing.db"
        app.DB_PATH = feed.DB = testdb
        admin.UPLOADS = Path(self.tmp.name) / "pictures"
        self.secrets = patch.dict(os.environ, {
            "FIGHTBASE_ADMIN_PASSWORD":"SuperSafeBulkPassword-1234",
            "FIGHTBASE_SECRET_KEY":"a" * 45,
        })
        self.secrets.start()
        app.init_db()
        feed.init_feed()
        admin.ensure_tables()
        feed.save_fighter({"id":"bulk-1","name":"Bulk Boxer One"})
        feed.save_fighter({"id":"bulk-2","name":"Bulk Boxer Two"})
        self.client = app.app.test_client()

    def tearDown(self):
        self.secrets.stop()
        app.DB_PATH = self.old_app_db
        feed.DB = self.old_feed_db
        admin.UPLOADS = self.old_uploads
        self.tmp.cleanup()

    def token(self):
        with self.client.session_transaction() as session:
            return session["fightbase_csrf"]

    def log_in(self):
        self.client.get("/admin/login")
        response = self.client.post("/admin/login", data={
            "csrf_token": self.token(),
            "password":"SuperSafeBulkPassword-1234"
        })
        self.assertEqual(response.status_code, 302)

    def upload_zip(self, entries, overwrite=False):
        archive = make_zip(entries)
        return self.client.post("/admin/fotos/zip-import", data={
            "csrf_token": self.token(),
            "overwrite": "1" if overwrite else "",
            "archive":(archive, "boxer-fotos.zip"),
        }, content_type="multipart/form-data")

    def show_report(self, response):
        self.assertEqual(response.status_code,302)
        self.assertIn("/admin/fotos/zip-bericht/",response.location)
        page=self.client.get(response.location)
        self.assertEqual(page.status_code,200)
        return page

    def test_requires_admin_and_csrf(self):
        response=self.client.post("/admin/fotos/zip-import")
        self.assertEqual(response.status_code,403)
        self.log_in()
        zip_stream=make_zip([("Bulk Boxer One.png",make_png())])
        response=self.client.post("/admin/fotos/zip-import",data={
            "csrf_token":"wrong",
            "archive":(zip_stream,"images.zip"),
        },content_type="multipart/form-data")
        self.assertEqual(response.status_code,400)
        self.assertFalse(feed.rows("SELECT * FROM hub_admin_photos"))

    def test_exact_names_in_nested_folders_import_correctly(self):
        self.log_in()
        response=self.upload_zip([
            ("Fotos/Bulk Boxer One.png",make_png()),
            ("Bulk Boxer Two.png",make_png((120,30,90))),
        ])
        report=self.show_report(response)
        self.assertIn("2",report.get_data(as_text=True))
        photos=feed.rows("SELECT * FROM hub_admin_photos ORDER BY fighter_id")
        self.assertEqual(len(photos),2)
        self.assertEqual([r["fighter_id"] for r in photos],["bulk-1","bulk-2"])
        for photo in photos:
            self.assertTrue(photo["filename"].endswith(".webp"))
            picture=self.client.get("/media/boxer/"+photo["fighter_id"])
            self.assertEqual(picture.status_code,200)
            with Image.open(io.BytesIO(picture.data)) as opened:
                self.assertEqual(opened.format,"WEBP")
        api=self.client.get("/api/foto/bulk-1")
        self.assertTrue(api.json["manual"])

    def test_ambiguous_names_require_explicit_id(self):
        feed.save_fighter({"id":"bulk-same-a","name":"Same Boxer"})
        feed.save_fighter({"id":"bulk-same-b","name":"Same Boxer"})
        self.log_in()
        report=self.show_report(self.upload_zip([
            ("Same Boxer.jpg",make_png()),
        ]))
        self.assertIn("Mehrere Boxerprofile",report.get_data(as_text=True))
        self.assertFalse(feed.rows(
            "SELECT * FROM hub_admin_photos WHERE fighter_id LIKE 'bulk-same-%'"))
        report=self.show_report(self.upload_zip([
            ("Same Boxer__bulk-same-a.png",make_png()),
        ]))
        self.assertIn("Same Boxer",report.get_data(as_text=True))
        photo=feed.one("SELECT * FROM hub_admin_photos WHERE fighter_id='bulk-same-a'")
        self.assertIsNotNone(photo)
        self.assertIsNone(feed.one(
            "SELECT * FROM hub_admin_photos WHERE fighter_id='bulk-same-b'"))

    def test_existing_image_not_overwritten_unless_selected(self):
        self.log_in()
        self.show_report(self.upload_zip([("Bulk Boxer One.png",make_png())]))
        old=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id='bulk-1'")["filename"]
        skip=self.show_report(self.upload_zip([
            ("Bulk Boxer One.png",make_png((10,220,60))),
        ]))
        self.assertIn("bereits vorhanden",skip.get_data(as_text=True))
        unchanged=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id='bulk-1'")["filename"]
        self.assertEqual(unchanged,old)
        replaced=self.show_report(self.upload_zip([
            ("Bulk Boxer One.png",make_png((10,220,60))),
        ],overwrite=True))
        self.assertIn("Bestehendes Foto ersetzt",replaced.get_data(as_text=True))
        new=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id='bulk-1'")["filename"]
        self.assertNotEqual(new,old)
        self.assertFalse((admin.UPLOADS/old).exists())

    def test_two_zip_entries_for_same_profile_are_both_skipped(self):
        self.log_in()
        report=self.show_report(self.upload_zip([
            ("Bulk Boxer One.png",make_png()),
            ("Bulk Boxer One.jpg",make_png()),
        ]))
        self.assertIn("Mehrere Fotos",report.get_data(as_text=True))
        self.assertIsNone(feed.one(
            "SELECT * FROM hub_admin_photos WHERE fighter_id='bulk-1'"))

    def test_rejects_paths_fake_images_and_foreign_ids(self):
        self.log_in()
        report=self.show_report(self.upload_zip([
            ("../Bulk Boxer One.png",make_png()),
            ("Bulk Boxer Two.png",b"this is not an image"),
            ("Bulk Boxer One__bulk-2.png",make_png()),
            ("Unknown Boxer.jpg",make_png()),
        ]))
        html=report.get_data(as_text=True)
        self.assertIn("Ungültiger Dateipfad",html)
        self.assertIn("Bild ungültig",html)
        self.assertIn("Boxer-ID oder Name passt nicht",html)
        self.assertIn("Kein Boxer",html)
        self.assertFalse(feed.rows("SELECT * FROM hub_admin_photos"))

    def test_invalid_zip_too_many_and_bomb_header_rejected(self):
        self.log_in()
        invalid=self.client.post("/admin/fotos/zip-import",data={
          "csrf_token":self.token(),"archive":(io.BytesIO(b"bad"),"fotos.zip"),
        },content_type="multipart/form-data")
        self.assertEqual(invalid.status_code,302)
        self.assertIn("#zip-fotos",invalid.location)
        too_many=[(f"Bulk Boxer {i}.png",b"x") for i in range(251)]
        rejected=self.upload_zip(too_many)
        self.assertIn("#zip-fotos",rejected.location)
        self.assertFalse(feed.rows("SELECT * FROM hub_admin_photos"))

    def test_zip_report_requires_login(self):
        self.log_in()
        result=self.upload_zip([("Bulk Boxer One.png",make_png())])
        path=result.location
        self.client.post("/admin/logout",data={"csrf_token":self.token()})
        self.assertIn("/admin/login",self.client.get(path).location)


if __name__=="__main__":
    unittest.main()
