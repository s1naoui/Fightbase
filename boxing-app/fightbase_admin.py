"""Fightbase local admin: image uploads and sourced fighter-record overrides.

Never commit passwords or uploaded images to Git. This admin is intended for
local development. Configure a password and stable Flask secret in .env.
"""
from __future__ import annotations
import hmac
import io
import os
import re
import secrets
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)
from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError
import boxing_feed as feed

bp=Blueprint("admin",__name__)
BASE=Path(__file__).resolve().parent
UPLOADS=BASE/"uploads"/"fighter_photos"
MAX_PHOTO_BYTES=5*1024*1024
Image.MAX_IMAGE_PIXELS=16_000_000
LOGIN_ERRORS={}

def configured():
    load_dotenv(BASE/".env")
    return bool(os.getenv("FIGHTBASE_ADMIN_PASSWORD","").strip() and
                os.getenv("FIGHTBASE_SECRET_KEY","").strip())

def signed_in():
    return configured() and session.get("fightbase_admin") is True

def csrf():
    if "fightbase_csrf" not in session:
        session["fightbase_csrf"]=secrets.token_urlsafe(32)
    return session["fightbase_csrf"]

def valid_csrf():
    expected=session.get("fightbase_csrf","")
    given=request.form.get("csrf_token","")
    return bool(expected and given and hmac.compare_digest(expected,given))

def init_admin(app):
    load_dotenv(BASE/".env")
    app.secret_key=os.getenv("FIGHTBASE_SECRET_KEY") or secrets.token_bytes(32)
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=45),
        MAX_CONTENT_LENGTH=6*1024*1024,
    )
    with feed.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS hub_admin_photos(
            fighter_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            source_url TEXT,
            updated_at TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS hub_admin_records(
            fighter_id TEXT PRIMARY KEY,
            wins INTEGER, losses INTEGER, draws INTEGER, ko_wins INTEGER,
            source_url TEXT NOT NULL, updated_at TEXT NOT NULL)""")
    app.register_blueprint(bp)

def apply_manual_records():
    """Reapply user's sourced corrections after seeded stat refresh."""
    with feed.connect() as db:
        try:
            db.execute("""UPDATE hub_fighters SET
               wins=(SELECT r.wins FROM hub_admin_records r WHERE r.fighter_id=hub_fighters.id),
               losses=(SELECT r.losses FROM hub_admin_records r WHERE r.fighter_id=hub_fighters.id),
               draws=(SELECT r.draws FROM hub_admin_records r WHERE r.fighter_id=hub_fighters.id),
               ko_wins=(SELECT r.ko_wins FROM hub_admin_records r WHERE r.fighter_id=hub_fighters.id),
               updated_at=(SELECT r.updated_at FROM hub_admin_records r WHERE r.fighter_id=hub_fighters.id)
               WHERE id IN (SELECT fighter_id FROM hub_admin_records)""")
        except Exception as exc:
            if "no such table" not in str(exc):
                raise

def get_photo(fighter_id):
    row=feed.one("SELECT * FROM hub_admin_photos WHERE fighter_id=?",(fighter_id,))
    if not row:
        return None
    filename=row["filename"]
    if not re.fullmatch(r"[0-9a-f]{32}\.webp", filename):
        return None
    if not (UPLOADS/filename).is_file():
        return None
    return {"url":url_for("admin.photo",fighter_id=fighter_id,v=row["updated_at"]),
            "source":row["source_url"],"pending":False,
            "manual":True}

def get_manual_record(fighter_id):
    return feed.one("SELECT * FROM hub_admin_records WHERE fighter_id=?",(fighter_id,))

def _fighter_or_404(fighter_id):
    if len(fighter_id)>100:
        abort(404)
    row=feed.one("SELECT * FROM hub_fighters WHERE id=?",(fighter_id,))
    if row is None:
        abort(404)
    return row

@bp.route("/admin/login",methods=["GET","POST"])
def login():
    if not configured():
        return render_template("admin_login.html",ready=False,token=None)
    if signed_in():
        return redirect(url_for("admin.dashboard"))
    message=None
    if request.method=="POST":
        ip=request.remote_addr or "local"
        attempts,last=LOGIN_ERRORS.get(ip,(0,0))
        if attempts>=5 and time.monotonic()-last < 60:
            message="Zu viele Versuche. Bitte eine Minute warten."
        elif not valid_csrf():
            abort(400,"Ungültiger Sicherheitstoken. Seite neu laden.")
        else:
            expected=os.getenv("FIGHTBASE_ADMIN_PASSWORD","")
            supplied=request.form.get("password","")
            if hmac.compare_digest(supplied.encode(),expected.encode()):
                LOGIN_ERRORS.pop(ip,None)
                session.clear()
                session["fightbase_admin"]=True
                session.permanent=True
                csrf()
                return redirect(url_for("admin.dashboard"))
            LOGIN_ERRORS[ip]=(attempts+1,time.monotonic())
            message="Passwort nicht korrekt."
    return render_template("admin_login.html",ready=True,message=message,token=csrf())

@bp.post("/admin/logout")
def logout():
    if not valid_csrf():
        abort(400)
    session.clear()
    return redirect(url_for("admin.login"))

@bp.get("/admin")
def dashboard():
    if not signed_in():
        return redirect(url_for("admin.login"))
    q=request.args.get("q","").strip()[:80]
    if len(q)>=2:
        fighters=feed.fighters(q)
    else:
        fighters=feed.fighters()[:30]
    photo_rows={r["fighter_id"]:r for r in feed.rows("SELECT * FROM hub_admin_photos")}
    record_rows={r["fighter_id"]:r for r in feed.rows("SELECT * FROM hub_admin_records")}
    return render_template("admin_dashboard.html",status=feed.status(),page="admin",
        fighters=fighters,q=q,photos=photo_rows,records=record_rows,token=csrf())

@bp.get("/media/boxer/<fighter_id>")
def photo(fighter_id):
    _fighter_or_404(fighter_id)
    row=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id=?",(fighter_id,))
    if not row or not re.fullmatch(r"[0-9a-f]{32}\.webp",row["filename"]):
        abort(404)
    path=UPLOADS/row["filename"]
    if not path.is_file():
        abort(404)
    response=send_file(path,mimetype="image/webp",conditional=True,max_age=300)
    response.headers["X-Content-Type-Options"]="nosniff"
    return response

def _require_admin_post():
    if not signed_in():
        abort(403,"Admin-Anmeldung erforderlich")
    if not valid_csrf():
        abort(400,"Ungültiger Sicherheitstoken")

def _back(fighter_id):
    return redirect(url_for("admin.dashboard",q=request.form.get("q","")[:80])+
                    "#fighter-"+fighter_id)

@bp.post("/admin/boxer/<fighter_id>/foto")
def upload_photo(fighter_id):
    _require_admin_post()
    person=_fighter_or_404(fighter_id)
    upload=request.files.get("photo")
    if not upload or not upload.filename:
        flash("Bitte ein Bild auswählen.","error")
        return _back(fighter_id)
    data=upload.stream.read(MAX_PHOTO_BYTES+1)
    if len(data)>MAX_PHOTO_BYTES:
        flash("Das Bild ist zu groß (maximal 5 MB).","error")
        return _back(fighter_id)
    try:
        with Image.open(io.BytesIO(data)) as original:
            original.verify()
        with Image.open(io.BytesIO(data)) as original:
            if original.format not in ("JPEG","PNG","WEBP"):
                raise ValueError("Nur JPG, PNG oder WebP sind erlaubt.")
            original=ImageOps.exif_transpose(original)
            if original.width < 250 or original.height < 250:
                raise ValueError("Das Foto muss mindestens 250 × 250 Pixel haben.")
            original.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            converted=original.convert("RGB")
            output=io.BytesIO()
            converted.save(output,format="WEBP",quality=86,method=5)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as e:
        flash("Ungültiges oder beschädigtes Bild: "+str(e)[:120],"error")
        return _back(fighter_id)
    url=request.form.get("source_url","").strip()[:500]
    if url and (urlsplit(url).scheme not in ("http","https")
                or not urlsplit(url).netloc):
        flash("Bildquelle muss eine gültige http(s)-Adresse sein.","error")
        return _back(fighter_id)
    UPLOADS.mkdir(parents=True,exist_ok=True)
    filename=uuid.uuid4().hex+".webp"
    (UPLOADS/filename).write_bytes(output.getvalue())
    previous=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id=?",(fighter_id,))
    with feed.connect() as db:
        db.execute("""INSERT INTO hub_admin_photos(fighter_id,filename,source_url,updated_at)
          VALUES(?,?,?,?) ON CONFLICT(fighter_id) DO UPDATE SET
          filename=excluded.filename,source_url=excluded.source_url,
          updated_at=excluded.updated_at""",
          (fighter_id,filename,url or None,feed.utcnow()))
    if previous and re.fullmatch(r"[0-9a-f]{32}\.webp",previous["filename"]):
        (UPLOADS/previous["filename"]).unlink(missing_ok=True)
    flash("Foto für "+person["name"]+" erfolgreich übernommen.","success")
    return _back(fighter_id)

@bp.post("/admin/boxer/<fighter_id>/foto/loeschen")
def delete_photo(fighter_id):
    _require_admin_post()
    _fighter_or_404(fighter_id)
    old=feed.one("SELECT filename FROM hub_admin_photos WHERE fighter_id=?",(fighter_id,))
    with feed.connect() as db:
        db.execute("DELETE FROM hub_admin_photos WHERE fighter_id=?",(fighter_id,))
    if old and re.fullmatch(r"[0-9a-f]{32}\.webp",old["filename"]):
        (UPLOADS/old["filename"]).unlink(missing_ok=True)
    flash("Eigenes Foto entfernt. Automatische Bildsuche ist wieder aktiv.","success")
    return _back(fighter_id)

@bp.post("/admin/boxer/<fighter_id>/bilanz")
def save_record(fighter_id):
    _require_admin_post()
    person=_fighter_or_404(fighter_id)
    try:
        numbers={}
        for key in ("wins","losses","draws","ko_wins"):
            raw=request.form.get(key,"").strip()
            if not raw.isdecimal() or not 0<=int(raw)<=150:
                raise ValueError("Ungültiger Wert für "+key+" (0–150).")
            numbers[key]=int(raw)
        if numbers["ko_wins"]>numbers["wins"]:
            raise ValueError("KO-Siege dürfen die Anzahl der Siege nicht überschreiten.")
        source=request.form.get("source_url","").strip()[:500]
        parsed=urlsplit(source)
        if parsed.scheme not in ("http","https") or not parsed.netloc:
            raise ValueError("Bitte eine öffentliche Quellen-URL (https://...) eintragen.")
    except ValueError as error:
        flash(str(error),"error")
        return _back(fighter_id)
    now=feed.utcnow()
    with feed.connect() as db:
        db.execute("""INSERT INTO hub_admin_records(
           fighter_id,wins,losses,draws,ko_wins,source_url,updated_at)
           VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(fighter_id) DO UPDATE SET
           wins=excluded.wins,losses=excluded.losses,draws=excluded.draws,
           ko_wins=excluded.ko_wins,source_url=excluded.source_url,
           updated_at=excluded.updated_at""",
           (fighter_id,numbers["wins"],numbers["losses"],numbers["draws"],
            numbers["ko_wins"],source,now))
        db.execute("""UPDATE hub_fighters SET wins=?,losses=?,draws=?,
           ko_wins=?,updated_at=? WHERE id=?""",
           (numbers["wins"],numbers["losses"],numbers["draws"],
            numbers["ko_wins"],now,fighter_id))
    flash("Bilanz für "+person["name"]+" mit Quelle gespeichert.","success")
    return _back(fighter_id)

@bp.post("/admin/boxer/<fighter_id>/bilanz/zuruecksetzen")
def reset_record(fighter_id):
    _require_admin_post()
    _fighter_or_404(fighter_id)
    with feed.connect() as db:
        db.execute("DELETE FROM hub_admin_records WHERE fighter_id=?",(fighter_id,))
    # An existing seeded record will be restored on the next app restart.
    flash("Manuelle Bilanz-Änderung zurückgesetzt. Nach Neustart gelten wieder die Quelldaten.","success")
    return _back(fighter_id)
