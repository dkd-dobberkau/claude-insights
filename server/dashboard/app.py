import os
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, render_template_string, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")


def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>dkd Claude Insights</title>
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {
            --bg: #1a1a2e;
            --bg-card: #16213e;
            --text: #eee;
            --text-dim: #888;
            --accent: #0f3460;
            --highlight: #e94560;
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
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>dkd Claude Insights</h1>
            <nav>
                <a href="/" class="{{ 'active' if active == 'team' else '' }}">Team</a>
                <a href="/tools" class="{{ 'active' if active == 'tools' else '' }}">Tools</a>
            </nav>
        </header>
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

HOME_TEMPLATE = """
{% extends "base" %}
{% block content %}
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
{% endblock %}
"""

TOOLS_TEMPLATE = """
{% extends "base" %}
{% block content %}
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
                <td>{{ "{:.0%}".format(tool.success_rate) }}</td>
                <td style="width: 200px;">
                    <div class="bar" style="width: {{ (tool.total_calls / max_calls * 100) | int }}%"></div>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
{% endblock %}
"""


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def home():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Team stats
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

            # Leaderboard
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

    return render_template_string(
        HOME_TEMPLATE,
        base=BASE_TEMPLATE,
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

    return render_template_string(
        TOOLS_TEMPLATE,
        base=BASE_TEMPLATE,
        active="tools",
        tools=tools_data,
        max_calls=max_calls
    )


if __name__ == "__main__":
    app.jinja_env.globals["base"] = BASE_TEMPLATE
    app.run(host="0.0.0.0", port=8081, debug=False)
