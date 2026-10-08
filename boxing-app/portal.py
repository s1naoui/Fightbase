"""Routes for the Fightbase boxing news and results hub."""
from datetime import datetime, date
from flask import Blueprint, render_template, jsonify, request, redirect, url_for, abort
from prediction import calculate_probability, calculate_three_way
import boxing_feed as feed

bp=Blueprint("hub",__name__)

@bp.app_template_filter("fightdate")
def fightdate(value):
    if not value:
        return "Datum offen"
    try:
        return datetime.fromisoformat(value.replace("Z","+00:00")).strftime("%d.%m.%Y")
    except ValueError:
        return str(value)[:10]

@bp.route("/")
def dashboard():
    feed.trigger_sync()
    tab=request.args.get("tab")
    if tab is None:
        # Show populated historical results when free live schedules are empty.
        tab="upcoming" if feed.upcoming() else "results"
    if tab not in ("upcoming","results","fighters","events","rankings","organizations"):
        tab="upcoming"
    search=request.args.get("q","").strip()[:80]
    event=request.args.get("event","").strip()[:80]
    division=request.args.get("division",1,type=int)
    if division not in range(1,18):
        division=1
    if tab=="fighters" and len(search)>=3:
        feed.search_fighter(search)
    upcoming=[f for f in feed.event_fights(event) if feed._has_two_boxers(f["a_name"],f["b_name"])] if event else feed.search_fights(search,"upcoming") if tab=="upcoming" else feed.upcoming()
    results=feed.search_fights(search,"results") if tab=="results" else feed.results()
    organizations=[o for o in feed.ORGANIZATIONS if search.casefold() in
       (o["code"]+" "+o["name"]).casefold()] if tab=="organizations" else feed.ORGANIZATIONS
    return render_template("hub_dashboard.html",page="dashboard",tab=tab,
      status=feed.status(),upcoming=upcoming,results=results,
      fighters=feed.fighters(search if tab=="fighters" else ""),events=feed.events(),
      ranking=feed.rankings(division) if tab=="rankings" else [],
      division=division,divisions=feed.DIVISIONS,search=search,event=event,
      archive_count=feed.archive_count(),fighters_count=feed.fighters_count(),organizations=organizations)

@bp.route("/kampf/<fight_id>")
def fight(fight_id):
    if len(fight_id)>100:
        abort(404)
    row=feed.one("SELECT * FROM hub_fights WHERE id=?",(fight_id,))
    if not row:
        abort(404)
    if not feed._has_two_boxers(row["a_name"], row["b_name"]):
        return redirect(url_for("hub.dashboard", tab="events"))
    a=feed.fighter_detail(row["a_id"]) if row["a_id"] else None
    b=feed.fighter_detail(row["b_id"]) if row["b_id"] else None
    probability=None
    if row["status"] in ("NOT_STARTED","LIVE") and row["fight_date"][:10]>=date.today().isoformat() and a and b and all(
        x[field] is not None for x in (a,b) for field in ("wins","losses")
    ):
        try:
            probability=calculate_three_way(
                {"name":a["name"],"age":a["age"],"wins":a["wins"],"losses":a["losses"]},
                {"name":b["name"],"age":b["age"],"wins":b["wins"],"losses":b["losses"]})
        except (KeyError,ZeroDivisionError,TypeError,ValueError):
            pass
    reference=feed.one("SELECT * FROM hub_sources WHERE entity_id=?",(fight_id,))
    return render_template("hub_fight.html",page="fight",status=feed.status(),
        fight=row,a=a,b=b,probability=probability,reference=reference)

@bp.route("/kampf/<fight_id>/analysieren",methods=["POST"])
def analyse(fight_id):
    row=feed.one("SELECT * FROM hub_fights WHERE id=?",(fight_id,))
    if not row:
        abort(404)
    a=feed.fighter_detail(row["a_id"]) if row["a_id"] else None
    b=feed.fighter_detail(row["b_id"]) if row["b_id"] else None
    if row["status"] != "NOT_STARTED" or row["fight_date"][:10]<date.today().isoformat() or not a or not b or any(x[key] is None for x in (a,b) for key in ("wins","losses")):
        return redirect(url_for("hub.fight",fight_id=fight_id))
    result=calculate_probability(
        {"name":a["name"],"age":a["age"],"wins":a["wins"],"losses":a["losses"]},
        {"name":b["name"],"age":b["age"],"wins":b["wins"],"losses":b["losses"]})
    with feed.connect() as c:
        cursor=c.execute("""INSERT INTO history
           (name_a,age_a,wins_a,losses_a,name_b,age_b,wins_b,losses_b,
            probability_a,probability_b,created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
           (a["name"],a["age"],a["wins"],a["losses"],b["name"],b["age"],
            b["wins"],b["losses"],float(result["probability_a"]),
            float(result["probability_b"]),datetime.now().strftime("%d.%m.%Y %H:%M")))
        pk=cursor.lastrowid
    return redirect(url_for("home",load=pk)+"#prediction")

@bp.route("/boxer/<fighter_id>")
def fighter(fighter_id):
    if len(fighter_id)>100:
        abort(404)
    person=feed.fighter_detail(fighter_id)
    if not person:
        abort(404)
    matches=feed.rows("""SELECT * FROM hub_fights WHERE a_id=? OR b_id=?
      ORDER BY fight_date DESC LIMIT 35""",(fighter_id,fighter_id))
    reference=feed.one("SELECT * FROM hub_sources WHERE entity_id=?",(fighter_id,))
    return render_template("hub_fighter.html",page="fighter",status=feed.status(),
       fighter=person,matches=matches,reference=reference)

@bp.route("/api/foto/<fighter_id>")
def photo(fighter_id):
    if len(fighter_id)>100:
        abort(404)
    person=feed.one("SELECT * FROM hub_fighters WHERE id=?",(fighter_id,))
    if not person:
        abort(404)
    from identity_photos import quick_verified_photo
    from fightbase_admin import get_photo
    uploaded=get_photo(fighter_id)
    if uploaded:
        return jsonify(uploaded)
    return jsonify(quick_verified_photo(fighter_id,person["name"]))

@bp.route("/api/status")
def status():
    feed.trigger_sync()
    return jsonify(feed.status())

def register_hub(app):
    feed.init_feed()
    app.register_blueprint(bp)
