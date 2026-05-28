import os
import re
from datetime import date, timedelta
from functools import wraps

import bcrypt
import pg8000.native
from urllib.parse import urlparse
from dotenv import load_dotenv
from flask import (Flask, g, jsonify, redirect, render_template,
                   request, session, url_for)

load_dotenv()

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static",
)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")


# ── DB connection ────────────────────────────────────────────────────────────

def parse_db_url(url):
    p = urlparse(url)
    return dict(
        host=p.hostname, port=p.port or 5432,
        database=p.path.lstrip("/"),
        user=p.username, password=p.password,
        ssl_context=True,
    )


class DictCursor:
    """Thin wrapper that makes pg8000 rows behave like dicts."""
    def __init__(self, conn):
        self._conn = conn
        self._rows = []
        self._cols = []

    def execute(self, sql, params=None):
        # pg8000 native uses $1,$2 placeholders + keyword args, convert %s → $1,$2...
        if params:
            converted = sql
            i = 1
            while "%s" in converted:
                converted = converted.replace("%s", f"${i}", 1)
                i += 1
            kwargs = {f"_{j+1}": v for j, v in enumerate(params)}
            result = self._conn.run(converted, **kwargs)
        else:
            result = self._conn.run(sql)
        self._rows = result if result else []
        self._cols = [c["name"] for c in self._conn.columns] if self._conn.columns else []
        return self

    def fetchone(self):
        if not self._rows:
            return None
        return dict(zip(self._cols, self._rows[0]))

    def fetchall(self):
        return [dict(zip(self._cols, r)) for r in self._rows]

    def __enter__(self): return self
    def __exit__(self, *a): pass


_db_cache = None

def get_db():
    global _db_cache
    # Reuse cached connection if still alive
    try:
        if _db_cache is not None:
            _db_cache.run("SELECT 1")
            if "db" not in g:
                g.db = _db_cache
            return g.db
    except Exception:
        _db_cache = None

    if "db" not in g:
        params = parse_db_url(os.environ["DATABASE_URL"])
        g.db = pg8000.native.Connection(**params)
        _db_cache = g.db
    return g.db


def db_cursor():
    return DictCursor(get_db())


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        try: db.close()
        except Exception: pass


# ── Auth helpers ─────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def current_user():
    if "user_id" not in session:
        return None
    db = get_db()
    with db_cursor() as cur:
        cur.execute("SELECT id, username, email FROM users WHERE id = %s",
                    (session["user_id"],))
        return cur.fetchone()


# ── Auth routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("monthly"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json() or request.form
    username = (data.get("username") or "").strip()
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    errors = {}
    if not username or len(username) < 3:
        errors["username"] = "Username must be at least 3 characters."
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors["email"] = "Enter a valid email."
    if len(password) < 6:
        errors["password"] = "Password must be at least 6 characters."

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with db_cursor() as cur:
            cur.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s) RETURNING id",
                (username, email, pw_hash),
            )
            user_id = cur.fetchone()["id"]
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            return jsonify({"ok": False, "errors": {"email": "Email or username already in use."}}), 409
        raise

    session["user_id"] = str(user_id)
    return jsonify({"ok": True, "redirect": url_for("monthly")})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json() or request.form
    email    = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    db = get_db()
    with db_cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE email = %s", (email,))
        user = cur.fetchone()

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return jsonify({"ok": False, "errors": {"email": "Invalid email or password."}}), 401

    session["user_id"] = str(user["id"])
    return jsonify({"ok": True, "redirect": url_for("monthly")})


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Page routes ───────────────────────────────────────────────────────────────

@app.route("/monthly")
@login_required
def monthly():
    return render_template("monthly.html", user=current_user())


@app.route("/weekly")
@login_required
def weekly():
    return render_template("weekly.html", user=current_user())


@app.route("/stats")
@login_required
def stats():
    return render_template("stats.html", user=current_user())


@app.route("/history")
@login_required
def history():
    return render_template("history.html", user=current_user())


# ── Goals API ─────────────────────────────────────────────────────────────────

@app.route("/api/goals", methods=["GET"])
@login_required
def get_goals():
    db = get_db()
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, emoji, category, frequency FROM goals WHERE user_id = %s ORDER BY created_at",
            (session["user_id"],),
        )
        return jsonify(cur.fetchall())


@app.route("/api/goals", methods=["POST"])
@login_required
def create_goal():
    data = request.get_json()
    name      = (data.get("name") or "").strip()
    emoji     = (data.get("emoji") or "🎯").strip()
    category  = (data.get("category") or "General").strip()
    frequency = (data.get("frequency") or "daily").strip()

    if not name:
        return jsonify({"error": "Name is required."}), 400

    db = get_db()
    with db_cursor() as cur:
        cur.execute(
            "INSERT INTO goals (user_id, name, emoji, category, frequency) VALUES (%s, %s, %s, %s, %s) RETURNING *",
            (session["user_id"], name, emoji, category, frequency),
        )
        goal = cur.fetchone()
    return jsonify(goal), 201


@app.route("/api/goals/<goal_id>", methods=["PUT"])
@login_required
def update_goal(goal_id):
    data = request.get_json()
    name      = (data.get("name") or "").strip()
    emoji     = (data.get("emoji") or "🎯").strip()
    category  = (data.get("category") or "General").strip()
    frequency = (data.get("frequency") or "daily").strip()

    if not name:
        return jsonify({"error": "Name is required."}), 400

    db = get_db()
    with db_cursor() as cur:
        cur.execute(
            """UPDATE goals SET name=%s, emoji=%s, category=%s, frequency=%s
               WHERE id=%s AND user_id=%s RETURNING *""",
            (name, emoji, category, frequency, goal_id, session["user_id"]),
        )
        goal = cur.fetchone()
    if not goal:
        return jsonify({"error": "Not found."}), 404
    return jsonify(goal)


@app.route("/api/goals/<goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id):
    db = get_db()
    with db_cursor() as cur:
        cur.execute(
            "DELETE FROM goals WHERE id=%s AND user_id=%s RETURNING id",
            (goal_id, session["user_id"]),
        )
        deleted = cur.fetchone()
    if not deleted:
        return jsonify({"error": "Not found."}), 404
    return jsonify({"ok": True})


# ── Checks API ────────────────────────────────────────────────────────────────

@app.route("/api/checks", methods=["GET"])
@login_required
def get_checks():
    year  = request.args.get("year",  date.today().year,  type=int)
    month = request.args.get("month", date.today().month, type=int)

    db = get_db()
    with db_cursor() as cur:
        cur.execute(
            """SELECT c.goal_id, c.checked_date
               FROM checks c
               JOIN goals g ON g.id = c.goal_id
               WHERE g.user_id = %s
                 AND EXTRACT(YEAR  FROM c.checked_date) = %s
                 AND EXTRACT(MONTH FROM c.checked_date) = %s""",
            (session["user_id"], year, month),
        )
        rows = cur.fetchall()

    # Return as {goal_id: [day, day, …]}
    result = {}
    for row in rows:
        gid = str(row["goal_id"])
        result.setdefault(gid, [])
        result[gid].append(row["checked_date"].day)
    return jsonify(result)


@app.route("/api/checks/toggle", methods=["POST"])
@login_required
def toggle_check():
    data    = request.get_json()
    goal_id = data.get("goal_id")
    day_str = data.get("date")           # "YYYY-MM-DD"

    try:
        checked_date = date.fromisoformat(day_str)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid date."}), 400

    # Prevent checking future dates
    if checked_date > date.today():
        return jsonify({"error": "Cannot check future dates."}), 400

    # Verify goal belongs to user
    db = get_db()
    with db_cursor() as cur:
        cur.execute("SELECT id FROM goals WHERE id=%s AND user_id=%s",
                    (goal_id, session["user_id"]))
        if not cur.fetchone():
            return jsonify({"error": "Goal not found."}), 404

        # Toggle
        cur.execute(
            "SELECT id FROM checks WHERE goal_id=%s AND checked_date=%s",
            (goal_id, checked_date),
        )
        existing = cur.fetchone()

        if existing:
            cur.execute("DELETE FROM checks WHERE id=%s", (existing["id"],))
            state = False
        else:
            cur.execute(
                "INSERT INTO checks (goal_id, checked_date) VALUES (%s, %s)",
                (goal_id, checked_date),
            )
            state = True

    return jsonify({"ok": True, "checked": state})


# ── Stats API ─────────────────────────────────────────────────────────────────

@app.route("/api/stats/monthly")
@login_required
def monthly_stats():
    year  = request.args.get("year",  date.today().year,  type=int)
    month = request.args.get("month", date.today().month, type=int)

    db = get_db()
    with db_cursor() as cur:
        # Total goals
        cur.execute("SELECT COUNT(*) AS cnt FROM goals WHERE user_id=%s", (session["user_id"],))
        total_goals = cur.fetchone()["cnt"]

        # Checks this month
        cur.execute(
            """SELECT COUNT(*) AS cnt FROM checks c
               JOIN goals g ON g.id = c.goal_id
               WHERE g.user_id=%s
                 AND EXTRACT(YEAR  FROM c.checked_date)=%s
                 AND EXTRACT(MONTH FROM c.checked_date)=%s""",
            (session["user_id"], year, month),
        )
        total_done = cur.fetchone()["cnt"]

        # Days elapsed
        today = date.today()
        if year == today.year and month == today.month:
            elapsed = today.day
        else:
            from calendar import monthrange
            elapsed = monthrange(year, month)[1]

        possible = total_goals * elapsed
        pct = round(total_done / possible * 100) if possible else 0

        # Best streak (all-goals-done streak)
        best_streak = 0
        cur_streak  = 0
        from calendar import monthrange
        days_in_month = monthrange(year, month)[1]
        for d in range(1, days_in_month + 1):
            cur.execute(
                """SELECT COUNT(*) AS cnt FROM checks c
                   JOIN goals g ON g.id = c.goal_id
                   WHERE g.user_id=%s AND c.checked_date=%s""",
                (session["user_id"], date(year, month, d)),
            )
            done_on_day = cur.fetchone()["cnt"]
            if total_goals > 0 and done_on_day >= total_goals:
                cur_streak += 1
                best_streak = max(best_streak, cur_streak)
            else:
                cur_streak = 0

    return jsonify({
        "total_goals":  total_goals,
        "total_done":   total_done,
        "possible":     possible,
        "pct":          pct,
        "best_streak":  best_streak,
        "elapsed_days": elapsed,
    })


@app.route("/api/stats/history")
@login_required
def history_stats():
    """Return last 6 months of per-goal completion data."""
    today = date.today()
    months = []
    for i in range(6):
        m = today.month - i
        y = today.year
        while m < 1:
            m += 12
            y -= 1
        months.append((y, m))

    from calendar import monthrange
    db = get_db()
    result = []
    with db_cursor() as cur:
        cur.execute(
            "SELECT id, name, emoji FROM goals WHERE user_id=%s ORDER BY created_at",
            (session["user_id"],),
        )
        goals = cur.fetchall()

        for (y, m) in months:
            days_in = monthrange(y, m)[1]
            if y == today.year and m == today.month:
                elapsed = today.day
            else:
                elapsed = days_in

            goal_stats = []
            total_done = 0
            for g in goals:
                cur.execute(
                    """SELECT COUNT(*) AS cnt FROM checks
                       WHERE goal_id=%s
                         AND EXTRACT(YEAR  FROM checked_date)=%s
                         AND EXTRACT(MONTH FROM checked_date)=%s""",
                    (g["id"], y, m),
                )
                done = cur.fetchone()["cnt"]
                total_done += done
                goal_stats.append({
                    "id":    str(g["id"]),
                    "name":  g["name"],
                    "emoji": g["emoji"],
                    "done":  done,
                    "total": elapsed,
                    "pct":   round(done / elapsed * 100) if elapsed else 0,
                })

            possible = len(goals) * elapsed
            result.append({
                "year":       y,
                "month":      m,
                "goals":      goal_stats,
                "total_done": total_done,
                "possible":   possible,
                "pct":        round(total_done / possible * 100) if possible else 0,
            })

    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)