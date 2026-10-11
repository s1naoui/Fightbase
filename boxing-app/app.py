
from flask import Flask, render_template, request, redirect, url_for
from prediction import calculate_probability
from pathlib import Path
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
DB_PATH = Path(__file__).resolve().parent / "fightbase.db"
# Für eine öffentliche Seite durch eine echte
# Projektadresse oder Kontaktadresse ergänzen.
HEADERS = {
    "User-Agent": "FightbaseStudentProject/2.0 (local educational project)",
    "Accept": "application/json"
}

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

    return render_template(
        "index.html",
        result=result,
        form_values=values,
        history=get_history(),
        analysis_id=analysis_id
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
from fightbase_admin import init_admin
init_admin(app)

if __name__ == "__main__":
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        from boxing_feed import start_scheduler
        start_scheduler()
    app.run(debug=True)
