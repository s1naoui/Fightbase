"""Fightbase admin for sourced boxer records, fight management and API sync."""
from __future__ import annotations
import hmac
import json
import threading
import os
import re
import secrets
import time
import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit
from flask import (Blueprint, abort, flash, jsonify, redirect, render_template,
                   request, session, url_for)
from dotenv import load_dotenv
import boxing_feed as feed

bp=Blueprint("admin",__name__)
BASE=Path(__file__).resolve().parent
LOGIN_ERRORS={}

def configured():
    load_dotenv(BASE/".env")
    password=os.getenv("FIGHTBASE_ADMIN_PASSWORD","").strip()
    secret=os.getenv("FIGHTBASE_SECRET_KEY","").strip()
    return len(password)>=10 and len(secret)>=32 and not (
        "DEIN_" in password.upper() or "HIER_" in secret.upper())

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
        MAX_CONTENT_LENGTH=70*1024*1024,  # 64 MB ZIP + multipart overhead
    )
    ensure_tables()
    app.register_blueprint(bp)
    apply_manual_records()

def ensure_tables():
    with feed.connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS hub_admin_records(
            fighter_id TEXT PRIMARY KEY,
            wins INTEGER, losses INTEGER, draws INTEGER, ko_wins INTEGER,
            source_url TEXT NOT NULL, updated_at TEXT NOT NULL)""")
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
        return render_template("admin_login.html",ready=False,token=None,status=feed.status(),page="admin")
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
    return render_template("admin_login.html",ready=True,message=message,token=csrf(),status=feed.status(),page="admin")

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
    record_rows={r["fighter_id"]:r for r in feed.rows("SELECT * FROM hub_admin_records")}
    mine=feed.rows("""SELECT * FROM hub_fights WHERE id LIKE 'manual-%'
        ORDER BY fight_date DESC LIMIT 30""")
    from boxing_rapidapi import usage
    return render_template("admin_dashboard.html",status=feed.status(),page="admin",
        fighters=fighters,q=q,records=record_rows,token=csrf(),
        manual_fights=mine,rapid=usage(),
        rapid_summary=json.loads(feed.meta("rapid_last_run_summary","{}") or "{}"))

def _require_admin_post():
    if not signed_in():
        abort(403,"Admin-Anmeldung erforderlich")
    if not valid_csrf():
        abort(400,"Ungültiger Sicherheitstoken")

def _back(fighter_id):
    return redirect(url_for("admin.dashboard",q=request.form.get("q","")[:80])+
                    "#fighter-"+fighter_id)

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
    person=_fighter_or_404(fighter_id)
    from verified_fights import RECORDS, fighter_key, AS_OF
    restored=next((record for record in RECORDS if fighter_key(record[0])==fighter_id),None)
    with feed.connect() as db:
        db.execute("DELETE FROM hub_admin_records WHERE fighter_id=?",(fighter_id,))
        if restored:
            _,wins,losses,draws,ko,*_=restored
            db.execute("""UPDATE hub_fighters SET wins=?,losses=?,draws=?,ko_wins=?,
                updated_at=? WHERE id=?""",
                (wins,losses,draws,ko,AS_OF,fighter_id))
        else:
            db.execute("""UPDATE hub_fighters SET wins=NULL,losses=NULL,draws=NULL,
                ko_wins=NULL,updated_at=? WHERE id=?""",
                (feed.utcnow(),fighter_id))
    flash("Manuelle Bilanz entfernt. Die ursprünglichen verifizierten Zahlen wurden wiederhergestellt"
          if restored else "Manuelle Bilanz entfernt. Ohne verifizierte Quelle sind die Werte jetzt unbekannt.",
          "success")
    return _back(fighter_id)


@bp.post("/admin/kampf")
def create_fight():
    """Manually enter sourced upcoming boxing fights absent from free APIs."""
    _require_admin_post()
    from datetime import date, datetime
    a=request.form.get("boxer_a","").strip()[:120]
    b=request.form.get("boxer_b","").strip()[:120]
    day=request.form.get("date","").strip()
    local_time=request.form.get("time","").strip()
    venue=request.form.get("venue","").strip()[:160]
    location=request.form.get("location","").strip()[:160]
    division=request.form.get("division","").strip()[:80]
    source=request.form.get("source_url","").strip()[:500]
    event=request.form.get("event","").strip()[:160]
    try:
        if not a or not b or a.casefold()==b.casefold():
            raise ValueError("Bitte zwei unterschiedliche Boxernamen eintragen.")
        if date.fromisoformat(day)<date.today():
            raise ValueError("Der Kampftermin muss heute oder in der Zukunft liegen.")
        if local_time:
            datetime.strptime(local_time,"%H:%M")
        if not venue or not location:
            raise ValueError("Veranstaltungsort und Stadt/Land sind erforderlich.")
        if not division:
            raise ValueError("Bitte Gewichtsklasse eintragen.")
        parsed=urlsplit(source)
        if parsed.scheme not in ("http","https") or not parsed.netloc:
            raise ValueError("Eine überprüfbare http(s)-Quellenadresse ist Pflicht.")
    except ValueError as exc:
        flash("Kampf nicht eingetragen: "+str(exc),"error")
        return redirect(url_for("admin.dashboard")+"#fight-editor")
    fight_id="manual-"+uuid.uuid4().hex
    event_id="event-"+fight_id
    start=day+("T"+local_time+":00" if local_time else "")
    with feed.connect() as db:
        identifiers=[]
        for boxer in (a,b):
            record=db.execute("""SELECT id FROM hub_fighters
                WHERE name=? COLLATE NOCASE
                ORDER BY CASE WHEN id LIKE 'reviewed-%' THEN 0 ELSE 1 END,id LIMIT 1""",
                (boxer,)).fetchone()
            if record:
                identifiers.append(record["id"])
            else:
                fid="manual-fighter-"+uuid.uuid4().hex
                db.execute("""INSERT INTO hub_fighters (id,name,division,updated_at)
                     VALUES(?,?,?,?)""",(fid,boxer,division,feed.utcnow()))
                identifiers.append(fid)
        db.execute("""INSERT INTO hub_events
            (id,title,event_date,venue,location,updated_at)
            VALUES(?,?,?,?,?,?)""",(event_id,event or a+" vs "+b,
                                    day,venue,location,feed.utcnow()))
        db.execute("""INSERT INTO hub_fights
            (id,fight_date,title,status,a_id,b_id,a_name,b_name,division,
             event_id,event_title,venue,location,updated_at)
             VALUES(?,?,?,'NOT_STARTED',?,?,?,?,?,?,?,?,?,?)""",
             (fight_id,start,a+" vs "+b,identifiers[0],identifiers[1],
              a,b,division,event_id,event or a+" vs "+b,venue,location,feed.utcnow()))
        db.execute("""INSERT INTO hub_sources
            (entity_id,source_url,reviewed_on,source_kind,time_note)
            VALUES(?,?,?,?,?)""",(fight_id,source,date.today().isoformat(),
                "admin-verified-schedule",
                "Veranstaltungsbeginn Ortszeit, nicht Ringwalk" if local_time
                else "Uhrzeit nicht bestätigt"))
    flash("Kampf eingetragen. Er erscheint im Kampfkalender.","success")
    return redirect(url_for("admin.dashboard")+"#fight-editor")

@bp.post("/admin/kampf/<fight_id>/loeschen")
def remove_fight(fight_id):
    _require_admin_post()
    if not re.fullmatch(r"manual-[a-f0-9]{32}",fight_id):
        abort(404)
    with feed.connect() as db:
        row=db.execute("SELECT event_id FROM hub_fights WHERE id=?",(fight_id,)).fetchone()
        if not row:
            abort(404)
        db.execute("DELETE FROM hub_fights WHERE id=?",(fight_id,))
        db.execute("DELETE FROM hub_sources WHERE entity_id=?",(fight_id,))
        db.execute("DELETE FROM hub_events WHERE id=?",(row["event_id"],))
    flash("Manuell eingetragener Kampf entfernt.","success")
    return redirect(url_for("admin.dashboard")+"#fight-editor")


# Manual API imports use the authenticated administrator's CSRF session.
# Manual synchronization runs in the background rather than blocking the page.
_RAPID_JOB_LOCK=threading.Lock()

@bp.post("/admin/boxing-api/test")
def test_boxing_api():
    _require_admin_post()
    from boxing_rapidapi import verify, ApiAccessError
    try:
        outcome=verify()  # one budgeted HTTP request
        flash(outcome["message"],"success")
    except ApiAccessError as exc:
        flash("API-Test: "+str(exc),"error")
    return redirect(url_for("admin.dashboard")+"#boxing-api")


def _refresh_boxing_job():
    try:
        from boxing_rapidapi import synchronize
        result=synchronize(force=True)
        feed.set_meta("rapid_last_run_summary",json.dumps(result,ensure_ascii=False))
    except Exception as exc:
        feed.set_meta("rapid_last_run_summary",json.dumps({
            "error":"Synchronisation fehlgeschlagen: "+type(exc).__name__
        },ensure_ascii=False))
    finally:
        _RAPID_JOB_LOCK.release()


@bp.post("/admin/boxing-api/sync")
def sync_boxing_api():
    _require_admin_post()
    from boxing_rapidapi import config, usage
    if not config()[0]:
        flash("Bitte zuerst einen kostenlosen RapidAPI-Schlüssel lokal in .env eintragen.","error")
    elif usage()["remaining"]==0:
        flash("Die Fightbase-Sicherheitsgrenze für diesen Monat ist erreicht.","error")
    elif not _RAPID_JOB_LOCK.acquire(blocking=False):
        flash("Die Synchronisierung läuft bereits. Aktualisiere die Seite in Kürze.","error")
    else:
        threading.Thread(target=_refresh_boxing_job,name="rapidapi-manual-sync",
                         daemon=True).start()
        flash("Synchronisierung gestartet. Bitte die Seite in wenigen Sekunden neu laden.","success")
    return redirect(url_for("admin.dashboard")+"#boxing-api")
