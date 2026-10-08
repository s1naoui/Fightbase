
from flask import Flask, render_template, request, redirect, url_for, jsonify
from prediction import calculate_probability
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3
import requests
import json
import re
import unicodedata

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "fightbase.db"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

# Für eine öffentliche Seite durch eine echte
# Projektadresse oder Kontaktadresse ergänzen.
HEADERS = {
    "User-Agent": "FightbaseStudentProject/2.0 (local educational project)",
    "Accept": "application/json"
}

# Häufig verwendete Kurzformen
ALIASES = {
    "usyk": "Oleksandr Usyk",
    "fury": "Tyson Fury",
    "tyson": "Mike Tyson",
    "canelo": "Canelo Alvarez",
    "crawford": "Terence Crawford",
    "inoue": "Naoya Inoue",
    "bivol": "Dmitry Bivol",
    "beterbiev": "Artur Beterbiev"
}

ACTION_WORDS = (
    "boxing", "fight", "fighting", "ring",
    "punch", "bout", "sparring", "match"
)

BAD_WORDS = (
    "poster", "logo", "signature", "autograph",
    "statue", "illustration", "drawing",
    "weigh-in", "weighing", "press conference"
)


def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    with get_db() as db:
        # Bestehender Verlauf bleibt erhalten.
        db.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name_a TEXT NOT NULL,
                age_a INTEGER NOT NULL,
                wins_a INTEGER NOT NULL,
                losses_a INTEGER NOT NULL,
                name_b TEXT NOT NULL,
                age_b INTEGER NOT NULL,
                wins_b INTEGER NOT NULL,
                losses_b INTEGER NOT NULL,
                probability_a REAL NOT NULL,
                probability_b REAL NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS photo_choices (
                fighter_key TEXT PRIMARY KEY,
                candidates TEXT NOT NULL,
                selected_index INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)


def normalize_name(name):
    name = unicodedata.normalize("NFKD", name)
    name = "".join(
        c for c in name
        if not unicodedata.combining(c)
    )
    return re.sub(r"\s+", " ", name.casefold()).strip()


def canonical_name(name):
    name = name.strip()
    return ALIASES.get(normalize_name(name), name)


def get_key(name):
    return normalize_name(canonical_name(name))


def get_history():
    with get_db() as db:
        return db.execute(
            "SELECT * FROM history ORDER BY id DESC"
        ).fetchall()


def save_analysis(a, b, result):
    with get_db() as db:
        cursor = db.execute("""
            INSERT INTO history (
                name_a, age_a, wins_a, losses_a,
                name_b, age_b, wins_b, losses_b,
                probability_a, probability_b, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            a["name"], a["age"], a["wins"], a["losses"],
            b["name"], b["age"], b["wins"], b["losses"],
            float(result["probability_a"]),
            float(result["probability_b"]),
            datetime.now().strftime("%d.%m.%Y %H:%M")
        ))
        return cursor.lastrowid


def read_photo_record(name):
    with get_db() as db:
        return db.execute(
            "SELECT * FROM photo_choices WHERE fighter_key = ?",
            (get_key(name),)
        ).fetchone()


def photo_score(title, name, width, height):
    """Heuristische Bewertung, keine Bilderkennung."""
    title = normalize_name(title.replace("File:", ""))

    full_name = normalize_name(name)
    tokens = [
        token for token in full_name.split()
        if len(token) > 2
    ]

    # Nur Kandidaten mit dem vollständigen Namen
    # oder sämtlichen Namensbestandteilen zulassen.
    if not tokens or not all(token in title for token in tokens):
        return -1000

    score = 20

    for word in ACTION_WORDS:
        if word in title:
            score += 8

    for word in BAD_WORDS:
        if word in title:
            score -= 18

    if width >= 800 and height >= 500:
        score += 4

    if width > height:
        score += 3

    return score


def search_photos(name):
    """Use only portraits of a uniquely identified Wikidata boxer."""
    from identity_photos import quick_verified_photo
    from boxing_feed import one
    canonical=canonical_name(name)
    row=one("SELECT id FROM hub_fighters WHERE lower(name)=lower(?) ORDER BY id LIMIT 1",
            (canonical,))
    key=row["id"] if row else "legacy-"+get_key(canonical)
    verified=quick_verified_photo(key,canonical)
    if not verified.get("url"):
        return []
    return [{"url":verified["url"],"source":verified["source"],"title":canonical,
             "score":100}]


def get_photo_gallery(name, refresh=False):
    """Reject previous unverified Commons matches; return one verified image."""
    photos=search_photos(name)
    return {"photos":photos,"selected":0}


def get_selected_photo(gallery):
    photos = gallery["photos"]
    index = gallery["selected"]

    if not photos:
        return None

    if 0 <= index < len(photos):
        return photos[index]

    return photos[0]


@app.route("/vergleich/verifiziertes-foto")
def verified_comparison_photo():
    from identity_photos import quick_verified_photo
    name = request.args.get("name", "").strip()
    if not 1 <= len(name) <= 120:
        return jsonify({"error":"Ungültiger Boxername"}),400
    canonical=canonical_name(name)
    key="legacy-"+get_key(canonical)
    return jsonify(quick_verified_photo(key,canonical))


@app.route("/vergleich", methods=["GET", "POST"])
def home():
    result = None
    values = {}
    analysis_id = None

    if request.method == "POST":
        try:
            a = {
                "name": request.form["name_a"].strip(),
                "age": int(request.form["age_a"]),
                "wins": int(request.form["wins_a"]),
                "losses": int(request.form["losses_a"])
            }

            b = {
                "name": request.form["name_b"].strip(),
                "age": int(request.form["age_b"]),
                "wins": int(request.form["wins_b"]),
                "losses": int(request.form["losses_b"])
            }

        except (KeyError, ValueError):
            return "Ungültige Eingabedaten", 400

        for boxer in (a, b):
            if (
                not boxer["name"]
                or len(boxer["name"]) > 120
                or not 1 <= boxer["age"] <= 120
                or boxer["wins"] < 0
                or boxer["losses"] < 0
            ):
                return "Ungültige Boxerdaten", 400

        result = calculate_probability(a, b)
        analysis_id = save_analysis(a, b, result)

        # Post/Redirect/Get verhindert doppelte Einträge
        # beim Aktualisieren der Webseite.
        return redirect(
            url_for("home", load=analysis_id, new=1)
            + "#prediction"
        )

    analysis_id = request.args.get("load", type=int)

    if analysis_id is not None:
        with get_db() as db:
            old = db.execute(
                "SELECT * FROM history WHERE id = ?",
                (analysis_id,)
            ).fetchone()

        if old:
            fields = [
                "name_a", "age_a", "wins_a", "losses_a",
                "name_b", "age_b", "wins_b", "losses_b"
            ]

            values = {
                field: old[field] for field in fields
            }

            result = {
                "name_a": old["name_a"],
                "name_b": old["name_b"],
                "probability_a": old["probability_a"],
                "probability_b": old["probability_b"]
            }

    galleries = {
        "a": {"photos": [], "selected": 0},
        "b": {"photos": [], "selected": 0}
    }

    if result:
        galleries["a"] = get_photo_gallery(result["name_a"])
        galleries["b"] = get_photo_gallery(result["name_b"])

    return render_template(
        "index.html",
        result=result,
        form_values=values,
        history=get_history(),
        galleries=galleries,
        analysis_id=analysis_id
    )


@app.route("/select-photo", methods=["POST"])
def select_photo():
    data = request.get_json(silent=True) or {}

    name = str(data.get("name", "")).strip()
    index = data.get("index")

    if not name or len(name) > 120 or type(index) is not int:
        return jsonify({"error": "Ungültige Auswahl"}), 400

    record = read_photo_record(name)

    if not record:
        return jsonify({"error":"Foto wird automatisch überprüft; manuelle Auswahl entfällt"}),400

    try:
        photos = json.loads(record["candidates"])
    except (ValueError, TypeError):
        return jsonify({"error": "Bilddaten fehlerhaft"}), 500

    if not 0 <= index < len(photos):
        return jsonify({"error": "Ungültiger Bildindex"}), 400

    with get_db() as db:
        db.execute("""
            UPDATE photo_choices
            SET selected_index = ?
            WHERE fighter_key = ?
        """, (index, get_key(name)))

    return jsonify({"success": True})


@app.route("/refresh-photos", methods=["POST"])
def refresh_photos():
    name = request.form.get("name", "").strip()
    analysis_id = request.form.get("analysis_id", type=int)

    if not name or len(name) > 120:
        return "Ungültiger Boxername", 400

    # Fotoaktualisierung nur für einen
    # tatsächlich gespeicherten Vergleich erlauben.
    with get_db() as db:
        old = db.execute(
            "SELECT name_a, name_b FROM history WHERE id = ?",
            (analysis_id,)
        ).fetchone()

    if not old or get_key(name) not in {
        get_key(old["name_a"]),
        get_key(old["name_b"])
    }:
        return "Analyse nicht gefunden", 404

    get_photo_gallery(name, refresh=True)

    return redirect(
        url_for("home", load=analysis_id) + "#prediction"
    )


@app.route("/delete/<int:analysis_id>", methods=["POST"])
def delete_analysis(analysis_id):
    with get_db() as db:
        db.execute(
            "DELETE FROM history WHERE id = ?",
            (analysis_id,)
        )

    return redirect(url_for("home") + "#verlauf")


@app.route("/clear-history", methods=["POST"])
def clear_history():
    with get_db() as db:
        db.execute("DELETE FROM history")

    return redirect(url_for("home") + "#verlauf")


init_db()
from portal import register_hub
register_hub(app)

if __name__ == "__main__":
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from boxing_feed import start_scheduler
        start_scheduler()
    app.run(debug=True)
