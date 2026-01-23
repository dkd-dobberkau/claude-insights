import os
import hashlib
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string, jsonify, session, redirect, request, url_for, flash
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# Support running under /dashboard/ subpath (Elestio deployment)
APPLICATION_ROOT = os.environ.get("APPLICATION_ROOT", "/dashboard/")
app.config["APPLICATION_ROOT"] = APPLICATION_ROOT

# Middleware to handle reverse proxy with subpath
class PrefixMiddleware:
    def __init__(self, app, prefix=''):
        self.app = app
        self.prefix = prefix.rstrip('/')

    def __call__(self, environ, start_response):
        if self.prefix:
            environ['SCRIPT_NAME'] = self.prefix
            path_info = environ.get('PATH_INFO', '')
            if path_info.startswith(self.prefix):
                environ['PATH_INFO'] = path_info[len(self.prefix):] or '/'
        return self.app(environ, start_response)

app.wsgi_app = PrefixMiddleware(app.wsgi_app, prefix=APPLICATION_ROOT)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def generate_api_key() -> str:
    return f"dkd_sk_{secrets.token_urlsafe(32)}"


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin-Zugang erforderlich", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>dkd Claude Insights</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <style>
        :root {
            --bg: #1a1a2e;
            --bg-card: #16213e;
            --text: #eee;
            --text-dim: #888;
            --accent: #0f3460;
            --highlight: #e94560;
            --success: #4ade80;
            --error: #ef4444;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--accent);
        }
        h1 { font-size: 1.5rem; }
        nav a {
            color: var(--text-dim);
            text-decoration: none;
            margin-left: 1.5rem;
            transition: color 0.2s;
        }
        nav a:hover, nav a.active { color: var(--highlight); }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }
        .stat-card {
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: var(--highlight);
        }
        .stat-label { color: var(--text-dim); font-size: 0.9rem; }
        .card {
            background: var(--bg-card);
            padding: 1.5rem;
            border-radius: 8px;
            margin-bottom: 1rem;
        }
        .card h2 { margin-bottom: 1rem; font-size: 1.1rem; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--accent); }
        th { color: var(--text-dim); font-weight: normal; }
        .bar {
            height: 8px;
            background: var(--highlight);
            border-radius: 4px;
        }
        .btn {
            display: inline-block;
            padding: 0.5rem 1rem;
            border-radius: 4px;
            text-decoration: none;
            cursor: pointer;
            border: none;
            font-size: 0.9rem;
            transition: opacity 0.2s;
        }
        .btn:hover { opacity: 0.8; }
        .btn-primary { background: var(--highlight); color: white; }
        .btn-secondary { background: var(--accent); color: white; }
        .btn-danger { background: var(--error); color: white; }
        .btn-sm { padding: 0.25rem 0.5rem; font-size: 0.8rem; }
        input, select {
            padding: 0.5rem;
            border: 1px solid var(--accent);
            border-radius: 4px;
            background: var(--bg);
            color: var(--text);
            font-size: 1rem;
        }
        input:focus, select:focus {
            outline: none;
            border-color: var(--highlight);
        }
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 0.5rem; color: var(--text-dim); }
        .flash { padding: 1rem; border-radius: 4px; margin-bottom: 1rem; }
        .flash-error { background: rgba(239, 68, 68, 0.2); border: 1px solid var(--error); }
        .flash-success { background: rgba(74, 222, 128, 0.2); border: 1px solid var(--success); }
        .login-box {
            max-width: 400px;
            margin: 4rem auto;
        }
        .api-key {
            font-family: monospace;
            background: var(--bg);
            padding: 0.5rem;
            border-radius: 4px;
            word-break: break-all;
        }
        .badge {
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
        }
        .badge-admin { background: var(--highlight); }
        .badge-active { background: var(--success); color: #000; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>dkd Claude Insights</h1>
            <nav>
                <a href="/" class="{{ 'active' if active == 'team' else '' }}">Team</a>
                <a href="/tools" class="{{ 'active' if active == 'tools' else '' }}">Tools</a>
                {% if session.get('is_admin') %}
                <a href="/admin/users" class="{{ 'active' if active == 'admin' else '' }}">Admin</a>
                <a href="/logout">Logout ({{ session.get('username') }})</a>
                {% else %}
                <a href="/login">Login</a>
                {% endif %}
            </nav>
        </header>
        {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
        {% for category, message in messages %}
        <div class="flash flash-{{ category }}">{{ message }}</div>
        {% endfor %}
        {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

HOME_CONTENT = """
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-value">{{ stats.total_sessions }}</div>
        <div class="stat-label">Sessions (7 Tage)</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:,.0f}".format(stats.total_tokens / 1000000) }}M</div>
        <div class="stat-label">Tokens</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:.0f}".format(stats.total_duration / 3600) }}h</div>
        <div class="stat-label">Coding-Zeit</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ stats.active_users }}</div>
        <div class="stat-label">Aktive Entwickler</div>
    </div>
</div>

<div class="card">
    <h2>Leaderboard (diese Woche)</h2>
    <table>
        <thead>
            <tr><th>#</th><th>Entwickler</th><th>Sessions</th><th>Tokens</th></tr>
        </thead>
        <tbody>
            {% for user in leaderboard %}
            <tr>
                <td>{{ user.rank }}</td>
                <td>{{ user.username }}</td>
                <td>{{ user.session_count }}</td>
                <td>{{ "{:,}".format(user.total_tokens) }}</td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

TOOLS_CONTENT = """
<div class="card">
    <h2>Meistgenutzte Tools (7 Tage)</h2>
    <table>
        <thead>
            <tr><th>Tool</th><th>Aufrufe</th><th>Erfolgsrate</th><th></th></tr>
        </thead>
        <tbody>
            {% for tool in tools %}
            <tr>
                <td>{{ tool.tool_name }}</td>
                <td>{{ "{:,}".format(tool.total_calls) }}</td>
                <td>{{ "{:.0%}".format(tool.success_rate or 0) }}</td>
                <td style="width: 200px;">
                    <div class="bar" style="width: {{ (tool.total_calls / max_calls * 100) | int }}%"></div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

LOGIN_CONTENT = """
<div class="login-box">
    <div class="card">
        <h2>Admin Login</h2>
        <form method="POST">
            <div class="form-group">
                <label>API Key</label>
                <input type="password" name="api_key" placeholder="dkd_sk_..." style="width: 100%;" required autofocus>
            </div>
            <button type="submit" class="btn btn-primary" style="width: 100%;">Login</button>
        </form>
    </div>
</div>
"""

ADMIN_USERS_CONTENT = """
<div class="card">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
        <h2>User-Verwaltung</h2>
        <a href="/admin/users/new" class="btn btn-primary">+ Neuer User</a>
    </div>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Share Level</th>
                <th>Status</th>
                <th>Sessions</th>
                <th>Letzter Sync</th>
                <th>Aktionen</th>
            </tr>
        </thead>
        <tbody>
            {% for user in users %}
            <tr>
                <td>{{ user.id }}</td>
                <td>
                    {{ user.username }}
                    {% if user.is_admin %}<span class="badge badge-admin">Admin</span>{% endif %}
                </td>
                <td>{{ user.email or '-' }}</td>
                <td>{{ user.share_level }}</td>
                <td>
                    {% if user.last_seen_at %}
                    <span class="badge badge-active">Aktiv</span>
                    {% else %}
                    <span style="color: var(--text-dim);">Nie</span>
                    {% endif %}
                </td>
                <td>{{ user.session_count }}</td>
                <td>{{ user.last_seen_at.strftime('%d.%m.%Y %H:%M') if user.last_seen_at else '-' }}</td>
                <td>
                    <form method="POST" action="/admin/users/{{ user.id }}/rotate-key" style="display: inline;">
                        <button type="submit" class="btn btn-secondary btn-sm" onclick="return confirm('Key rotieren?')">Key rotieren</button>
                    </form>
                    {% if user.id != session.get('user_id') %}
                    <form method="POST" action="/admin/users/{{ user.id }}/delete" style="display: inline;">
                        <button type="submit" class="btn btn-danger btn-sm" onclick="return confirm('User wirklich loeschen?')">Loeschen</button>
                    </form>
                    {% endif %}
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>

{% if new_api_key %}
<div class="card" style="border: 2px solid var(--success);">
    <h2>Neuer API Key generiert</h2>
    <p style="margin-bottom: 1rem;">Speichere diesen Key - er kann nicht erneut angezeigt werden!</p>
    <div class="api-key">{{ new_api_key }}</div>
</div>
{% endif %}
"""

NEW_USER_CONTENT = """
<div class="card" style="max-width: 500px;">
    <h2>Neuen User anlegen</h2>
    <form method="POST">
        <div class="form-group">
            <label>Username *</label>
            <input type="text" name="username" required style="width: 100%;">
        </div>
        <div class="form-group">
            <label>Email</label>
            <input type="email" name="email" style="width: 100%;">
        </div>
        <div class="form-group">
            <label>Share Level</label>
            <select name="share_level" style="width: 100%;">
                <option value="metadata" selected>metadata (Standard)</option>
                <option value="full">full</option>
                <option value="none">none</option>
            </select>
        </div>
        <div class="form-group">
            <label>
                <input type="checkbox" name="is_admin"> Admin-Rechte
            </label>
        </div>
        <button type="submit" class="btn btn-primary">User anlegen</button>
        <a href="/admin/users" class="btn btn-secondary">Abbrechen</a>
    </form>
</div>
"""


def render_page(content, **kwargs):
    """Render a page with the base template."""
    full_template = BASE_TEMPLATE.replace("{% block content %}{% endblock %}", content)
    return render_template_string(full_template, **kwargs)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        api_key = request.form.get("api_key", "").strip()
        key_hash = hash_api_key(api_key)

        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, username, is_admin FROM users WHERE api_key_hash = %s
                """, (key_hash,))
                user = cur.fetchone()

        if user and user["is_admin"]:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = True
            flash("Login erfolgreich", "success")
            return redirect(url_for("admin_users"))
        elif user:
            flash("Kein Admin-Zugang", "error")
        else:
            flash("Ungueltiger API Key", "error")

    return render_page(LOGIN_CONTENT, active="")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logout erfolgreich", "success")
    return redirect(url_for("home"))


@app.route("/admin/users")
@admin_required
def admin_users():
    new_api_key = session.pop("new_api_key", None)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    u.*,
                    COUNT(s.id) as session_count
                FROM users u
                LEFT JOIN sessions s ON s.user_id = u.id
                GROUP BY u.id
                ORDER BY u.username
            """)
            users = cur.fetchall()

    return render_page(
        ADMIN_USERS_CONTENT,
        active="admin",
        users=users,
        new_api_key=new_api_key
    )


@app.route("/admin/users/new", methods=["GET", "POST"])
@admin_required
def admin_new_user():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip() or None
        share_level = request.form.get("share_level", "metadata")
        is_admin = request.form.get("is_admin") == "on"

        if not username:
            flash("Username erforderlich", "error")
            return redirect(url_for("admin_new_user"))

        api_key = generate_api_key()
        key_hash = hash_api_key(api_key)

        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (username, api_key_hash, email, share_level, is_admin)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (username, key_hash, email, share_level, is_admin))
                    conn.commit()

            session["new_api_key"] = api_key
            flash(f"User '{username}' angelegt", "success")
            return redirect(url_for("admin_users"))
        except psycopg2.IntegrityError:
            flash(f"Username '{username}' existiert bereits", "error")

    return render_page(NEW_USER_CONTENT, active="admin")


@app.route("/admin/users/<int:user_id>/rotate-key", methods=["POST"])
@admin_required
def admin_rotate_key(user_id):
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users SET api_key_hash = %s WHERE id = %s RETURNING username
            """, (key_hash, user_id))
            result = cur.fetchone()
            conn.commit()

    if result:
        session["new_api_key"] = api_key
        flash(f"Neuer Key fuer '{result['username']}' generiert", "success")
    else:
        flash("User nicht gefunden", "error")

    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("Kann eigenen Account nicht loeschen", "error")
        return redirect(url_for("admin_users"))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT username FROM users WHERE id = %s", (user_id,))
            user = cur.fetchone()
            if user:
                cur.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM daily_stats WHERE user_id = %s", (user_id,))
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                conn.commit()
                flash(f"User '{user['username']}' geloescht", "success")
            else:
                flash("User nicht gefunden", "error")

    return redirect(url_for("admin_users"))


@app.route("/")
def home():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT id) as total_sessions,
                    COUNT(DISTINCT user_id) as active_users,
                    COALESCE(SUM(total_tokens_in + total_tokens_out), 0) as total_tokens,
                    COALESCE(SUM(duration_seconds), 0) as total_duration
                FROM sessions
                WHERE started_at >= NOW() - INTERVAL '7 days'
            """)
            stats = cur.fetchone()

            cur.execute("""
                SELECT
                    u.username,
                    COUNT(s.id) as session_count,
                    COALESCE(SUM(s.total_tokens_in + s.total_tokens_out), 0) as total_tokens
                FROM users u
                JOIN sessions s ON s.user_id = u.id
                WHERE u.show_in_leaderboard = true
                  AND s.started_at >= NOW() - INTERVAL '7 days'
                GROUP BY u.id
                ORDER BY total_tokens DESC
                LIMIT 10
            """)
            leaderboard = [
                {"rank": i + 1, **row}
                for i, row in enumerate(cur.fetchall())
            ]

    return render_page(
        HOME_CONTENT,
        active="team",
        stats=stats,
        leaderboard=leaderboard
    )


@app.route("/tools")
def tools():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    t.tool_name,
                    SUM(t.call_count) as total_calls,
                    SUM(t.success_count)::float / NULLIF(SUM(t.call_count), 0) as success_rate
                FROM tool_usage t
                JOIN sessions s ON t.session_id = s.id
                WHERE s.started_at >= NOW() - INTERVAL '7 days'
                GROUP BY t.tool_name
                ORDER BY total_calls DESC
                LIMIT 20
            """)
            tools_data = cur.fetchall()
            max_calls = tools_data[0]["total_calls"] if tools_data else 1

    return render_page(
        TOOLS_CONTENT,
        active="tools",
        tools=tools_data,
        max_calls=max_calls
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)
