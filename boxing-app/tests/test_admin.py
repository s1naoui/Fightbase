"""Admin authentication, safe image uploads, sourced records and fixture creation."""
import io
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from PIL import Image
import app
import boxing_feed as feed
import fightbase_admin as admin


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.old_db=app.DB_PATH
        self.old_feed=feed.DB
        self.old_uploads=admin.UPLOADS
        db=Path(self.tmp.name)/"test.db"
        app.DB_PATH=feed.DB=db
        admin.UPLOADS=Path(self.tmp.name)/"fighter_images"
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
        admin.UPLOADS=self.old_uploads
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
        self.assertEqual(self.client.post("/admin/boxer/"+self.fid+"/foto").status_code,403)
        self.login()
        self.assertEqual(self.client.get("/admin").status_code,200)
        response=self.client.post("/admin/boxer/"+self.fid+"/foto",
                                  data={"csrf_token":"wrong"})
        self.assertEqual(response.status_code,400)

    def test_upload_writes_webp_and_photo_api_prefers_it(self):
        self.login()
        original=io.BytesIO()
        Image.new("RGB",(900,1200),(55,80,120)).save(original,format="PNG")
        original.seek(0)
        result=self.client.post("/admin/boxer/"+self.fid+"/foto",
            data={"csrf_token":self.csrf(),"q":"Fury",
                  "photo":(original,"verified-photo.png"),
                  "source_url":"https://example.org/licensed-photo"},
            content_type="multipart/form-data")
        self.assertEqual(result.status_code,302)
        image=self.client.get("/api/foto/"+self.fid)
        self.assertEqual(image.status_code,200)
        self.assertTrue(image.json["manual"])
        self.assertIn("/media/boxer/",image.json["url"])
        picture=self.client.get(image.json["url"])
        self.assertEqual(picture.status_code,200)
        self.assertEqual(picture.mimetype,"image/webp")
        with Image.open(io.BytesIO(picture.data)) as rendered:
            self.assertEqual(rendered.format,"WEBP")
            self.assertLessEqual(max(rendered.size),1600)
        delete=self.client.post("/admin/boxer/"+self.fid+"/foto/loeschen",
                    data={"csrf_token":self.csrf(),"q":"Fury"})
        self.assertEqual(delete.status_code,302)
        self.assertEqual(self.client.get(image.json["url"]).status_code,404)

    def test_bad_content_and_oversize_are_rejected(self):
        self.login()
        wrong=self.client.post("/admin/boxer/"+self.fid+"/foto",
          data={"csrf_token":self.csrf(),"photo":(io.BytesIO(b"not-an-image"),"fake.png")},
          content_type="multipart/form-data")
        self.assertEqual(wrong.status_code,302)
        self.assertIsNone(feed.one("SELECT * FROM hub_admin_photos WHERE fighter_id=?",(self.fid,)))
        big=self.client.post("/admin/boxer/"+self.fid+"/foto",
          data={"csrf_token":self.csrf(),"photo":(io.BytesIO(b"x"*(5*1024*1024+1)),"big.png")},
          content_type="multipart/form-data")
        self.assertIn(big.status_code,(302,413))
        self.assertIsNone(feed.one("SELECT * FROM hub_admin_photos WHERE fighter_id=?",(self.fid,)))

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
