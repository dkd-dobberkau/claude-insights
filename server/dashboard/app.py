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


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Login erforderlich", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user_id"):
            flash("Login erforderlich", "error")
            return redirect(url_for("login"))
        if not session.get("is_admin"):
            flash("Admin-Zugang erforderlich", "error")
            return redirect(url_for("home"))
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
                {% if session.get('user_id') %}
                <a href="{{ url_for('home') }}" class="{{ 'active' if active == 'team' else '' }}">Team</a>
                <a href="{{ url_for('sessions_list') }}" class="{{ 'active' if active == 'sessions' else '' }}">Sessions</a>
                <a href="{{ url_for('tokens') }}" class="{{ 'active' if active == 'tokens' else '' }}">Tokens</a>
                <a href="{{ url_for('search') }}" class="{{ 'active' if active == 'search' else '' }}">Suche</a>
                <a href="{{ url_for('plans_list') }}" class="{{ 'active' if active == 'plans' else '' }}">Plaene</a>
                <a href="{{ url_for('tools') }}" class="{{ 'active' if active == 'tools' else '' }}">Tools</a>
                {% if session.get('is_admin') %}
                <a href="{{ url_for('admin_users') }}" class="{{ 'active' if active == 'admin' else '' }}">Admin</a>
                {% endif %}
                <a href="{{ url_for('logout') }}">Logout ({{ session.get('username') }})</a>
                {% else %}
                <a href="{{ url_for('login') }}">Login</a>
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
        <a href="{{ url_for('admin_new_user') }}" class="btn btn-primary">+ Neuer User</a>
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
        <a href="{{ url_for('admin_users') }}" class="btn btn-secondary">Abbrechen</a>
    </form>
</div>
"""

SESSIONS_CONTENT = """
<div class="card">
    <h2>{% if session.get('is_admin') %}Alle Sessions{% else %}Meine Sessions{% endif %}</h2>
    <table>
        <thead>
            <tr>
                {% if session.get('is_admin') %}<th>User</th>{% endif %}
                <th>Session-ID</th>
                <th>Projekt</th>
                <th>Datum</th>
                <th>Nachrichten</th>
                <th>Tokens</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for s in sessions %}
            <tr>
                {% if session.get('is_admin') %}<td>{{ s.username or '-' }}</td>{% endif %}
                <td style="font-family: monospace; font-size: 0.85rem;">{{ s.id[:20] }}...</td>
                <td>{{ s.project_name or '-' }}</td>
                <td>{{ s.started_at.strftime('%d.%m.%Y %H:%M') if s.started_at else '-' }}</td>
                <td>{{ s.total_messages }}</td>
                <td>{{ "{:,}".format(s.total_tokens_in + s.total_tokens_out) }}</td>
                <td><a href="{{ url_for('replay', session_id=s.id) }}" class="btn btn-sm btn-primary">Replay</a></td>
            </tr>
            {% else %}
            <tr><td colspan="{% if session.get('is_admin') %}7{% else %}6{% endif %}" style="text-align: center; color: var(--text-dim);">Keine Sessions vorhanden</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

REPLAY_CONTENT = """
<style>
    .replay-container { display: flex; gap: 1rem; min-height: 70vh; }
    .timeline { width: 280px; flex-shrink: 0; }
    .timeline-list { max-height: 60vh; overflow-y: auto; }
    .timeline-item {
        padding: 0.5rem 0.75rem;
        border-left: 3px solid var(--accent);
        margin-bottom: 0.25rem;
        cursor: pointer;
        font-size: 0.85rem;
        transition: background 0.2s;
    }
    .timeline-item:hover { background: var(--accent); }
    .timeline-item.active { background: var(--accent); border-left-color: var(--highlight); }
    .timeline-item.user { border-left-color: #42a5f5; }
    .timeline-item.assistant { border-left-color: #66bb6a; }
    .timeline-item .role { font-weight: bold; text-transform: uppercase; font-size: 0.7rem; color: var(--text-dim); }
    .timeline-item .preview { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text); }
    .message-view { flex: 1; }
    .message-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem; }
    .message-header .role-badge {
        padding: 0.25rem 0.75rem;
        border-radius: 4px;
        font-weight: bold;
        text-transform: uppercase;
        font-size: 0.75rem;
    }
    .role-badge.user { background: #1565c0; }
    .role-badge.assistant { background: #2e7d32; }
    .message-body {
        background: var(--bg);
        padding: 1.5rem;
        border-radius: 8px;
        white-space: pre-wrap;
        font-family: inherit;
        line-height: 1.7;
        max-height: 50vh;
        overflow-y: auto;
    }
    .message-body code { background: var(--accent); padding: 0.1rem 0.3rem; border-radius: 3px; font-family: monospace; }
    .message-body pre { background: var(--accent); padding: 1rem; border-radius: 4px; overflow-x: auto; margin: 1rem 0; }
    .message-body pre code { background: none; padding: 0; }
    .controls { display: flex; gap: 0.5rem; margin-bottom: 1rem; align-items: center; }
    .controls .position { color: var(--text-dim); margin-left: auto; }
    .tool-calls { margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--accent); }
    .tool-call {
        background: var(--bg);
        border-left: 3px solid #ff9800;
        padding: 0.75rem 1rem;
        margin: 0.5rem 0;
        border-radius: 0 4px 4px 0;
    }
    .tool-call .name { font-weight: bold; color: #ffb74d; margin-bottom: 0.5rem; }
    .tool-call pre { margin: 0.5rem 0 0 0; font-size: 0.85rem; }
    .no-messages { text-align: center; padding: 3rem; color: var(--text-dim); }
</style>

<div class="controls">
    <a href="{{ url_for('sessions_list') }}" class="btn btn-secondary">Zurueck</a>
    <button onclick="prev()" class="btn btn-secondary">Vorherige</button>
    <button onclick="next()" class="btn btn-secondary">Naechste</button>
    <span class="position" id="position">1 / {{ messages|length }}</span>
</div>

{% if messages %}
<div class="replay-container">
    <div class="timeline card">
        <h2 style="margin-bottom: 0.5rem;">Timeline</h2>
        <div class="timeline-list">
            {% for msg in messages %}
            <div class="timeline-item {{ msg.role }}" data-index="{{ loop.index0 }}" onclick="goTo({{ loop.index0 }})">
                <div class="role">{{ msg.role }}</div>
                {% if msg.content %}<div class="preview">{{ msg.content[:40]|e }}{% if msg.content|length > 40 %}...{% endif %}</div>{% endif %}
            </div>
            {% endfor %}
        </div>
    </div>
    <div class="message-view card">
        <div id="messageContainer"></div>
        <div class="tool-calls" id="toolCallsContainer" style="display: none;"></div>
    </div>
</div>

<script>
const messages = {{ messages_json|safe }};
const toolCalls = {{ tool_calls_json|safe }};
let currentIndex = 0;

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}

function renderMessage(index) {
    const msg = messages[index];
    const container = document.getElementById('messageContainer');
    let content = escapeHtml(msg.content);
    content = content.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, '<pre><code>$2</code></pre>');
    content = content.replace(/`([^`]+)`/g, '<code>$1</code>');

    container.innerHTML = `
        <div class="message-header">
            <span class="role-badge ${msg.role}">${msg.role}</span>
            <span style="color: var(--text-dim); font-size: 0.85rem;">${msg.timestamp || ''}</span>
        </div>
        <div class="message-body">${content}</div>
    `;

    // Tool calls
    const tcContainer = document.getElementById('toolCallsContainer');
    const msgTools = toolCalls.filter(tc => tc.message_id === msg.id);
    if (msgTools.length > 0) {
        tcContainer.style.display = 'block';
        tcContainer.innerHTML = '<h3 style="margin-bottom: 0.5rem;">Tool Calls</h3>' +
            msgTools.map(tc => `
                <div class="tool-call">
                    <div class="name">${escapeHtml(tc.tool_name)}</div>
                    ${tc.tool_input ? `<pre>${escapeHtml(tc.tool_input.substring(0, 500))}${tc.tool_input.length > 500 ? '...' : ''}</pre>` : ''}
                </div>
            `).join('');
    } else {
        tcContainer.style.display = 'none';
    }

    document.getElementById('position').textContent = `${index + 1} / ${messages.length}`;
    document.querySelectorAll('.timeline-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    document.querySelector('.timeline-item.active')?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function goTo(index) {
    currentIndex = Math.max(0, Math.min(index, messages.length - 1));
    renderMessage(currentIndex);
}

function prev() { goTo(currentIndex - 1); }
function next() { goTo(currentIndex + 1); }

document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft') prev();
    if (e.key === 'ArrowRight') next();
});

if (messages.length > 0) renderMessage(0);
</script>
{% else %}
<div class="card no-messages">
    <h2>Keine Nachrichten verfuegbar</h2>
    <p>Diese Session hat keine Nachrichten-Daten (share_level: {{ share_level }}).</p>
</div>
{% endif %}
"""

TOKENS_CONTENT = """
<div class="stats-grid">
    <div class="stat-card">
        <div class="stat-value">{{ "{:,}".format(totals.input_tokens) }}</div>
        <div class="stat-label">Eingabe-Tokens</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:,}".format(totals.output_tokens) }}</div>
        <div class="stat-label">Ausgabe-Tokens</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:,}".format(totals.cache_read) }}</div>
        <div class="stat-label">Cache-Lesen</div>
    </div>
    <div class="stat-card">
        <div class="stat-value">{{ "{:,}".format(totals.cache_creation) }}</div>
        <div class="stat-label">Cache-Erstellung</div>
    </div>
</div>

<div class="card">
    <h2>Nutzung nach Modell</h2>
    <table>
        <thead>
            <tr>
                <th>Modell</th>
                <th style="text-align: right;">Eingabe</th>
                <th style="text-align: right;">Ausgabe</th>
                <th style="text-align: right;">Cache-Lesen</th>
                <th style="text-align: right;">Cache-Erstellung</th>
                <th style="text-align: right;">Nachrichten</th>
            </tr>
        </thead>
        <tbody>
            {% for row in by_model %}
            <tr>
                <td><span style="font-family: monospace; background: var(--bg); padding: 0.2rem 0.5rem; border-radius: 4px;">{{ row.model }}</span></td>
                <td style="text-align: right;">{{ "{:,}".format(row.input_tokens) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.output_tokens) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.cache_read) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.cache_creation) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.message_count) }}</td>
            </tr>
            {% else %}
            <tr><td colspan="6" style="text-align: center; color: var(--text-dim);">Keine Daten</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>

<div class="card">
    <h2>Top Sessions nach Token-Nutzung</h2>
    <table>
        <thead>
            <tr>
                <th>Session</th>
                <th>Projekt</th>
                <th style="text-align: right;">Eingabe</th>
                <th style="text-align: right;">Ausgabe</th>
                <th style="text-align: right;">Gesamt</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for row in by_session %}
            <tr>
                <td style="font-family: monospace; font-size: 0.85rem;">{{ row.session_id[:20] }}...</td>
                <td>{{ row.project_name or '-' }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.input_tokens) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.output_tokens) }}</td>
                <td style="text-align: right;">{{ "{:,}".format(row.input_tokens + row.output_tokens) }}</td>
                <td><a href="{{ url_for('replay', session_id=row.session_id) }}" class="btn btn-sm btn-secondary">Replay</a></td>
            </tr>
            {% else %}
            <tr><td colspan="6" style="text-align: center; color: var(--text-dim);">Keine Daten</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

SEARCH_CONTENT = """
<div class="card">
    <h2>Prompt-Suche</h2>
    <form method="GET" style="margin-bottom: 1rem;">
        <input type="text" name="q" placeholder="Suche in deinen Nachrichten..." value="{{ query }}" style="width: 100%;" autofocus>
    </form>

    {% if results %}
    <p style="color: var(--text-dim); margin-bottom: 1rem;">{{ results|length }} Ergebnisse gefunden</p>
    <div style="max-height: 60vh; overflow-y: auto;">
        {% for r in results %}
        <div style="padding: 1rem; border-bottom: 1px solid var(--accent);">
            <div style="margin-bottom: 0.5rem;">{{ r.snippet|safe }}</div>
            <div style="font-size: 0.85rem; color: var(--text-dim);">
                {{ r.project_name or 'Unbekannt' }} &middot; {{ r.timestamp.strftime('%d.%m.%Y %H:%M') if r.timestamp else '' }}
                <a href="{{ url_for('replay', session_id=r.session_id) }}" style="margin-left: 1rem; color: var(--highlight);">Session anzeigen</a>
            </div>
        </div>
        {% endfor %}
    </div>
    {% elif query %}
    <p style="text-align: center; color: var(--text-dim); padding: 2rem;">Keine Ergebnisse fuer "{{ query }}"</p>
    {% else %}
    <p style="text-align: center; color: var(--text-dim); padding: 2rem;">Gib einen Suchbegriff ein</p>
    {% endif %}
</div>
"""

PLANS_CONTENT = """
<div class="card">
    <h2>Implementierungs-Plaene ({{ plans|length }})</h2>
    <table>
        <thead>
            <tr>
                <th>Titel</th>
                <th>Name</th>
                <th>Erstellt</th>
                <th></th>
            </tr>
        </thead>
        <tbody>
            {% for p in plans %}
            <tr>
                <td>{{ p.title or p.name }}</td>
                <td style="font-family: monospace; font-size: 0.85rem;">{{ p.name }}</td>
                <td>{{ p.created_at.strftime('%d.%m.%Y') if p.created_at else '-' }}</td>
                <td><a href="{{ url_for('plan_detail', name=p.name) }}" class="btn btn-sm btn-primary">Anzeigen</a></td>
            </tr>
            {% else %}
            <tr><td colspan="4" style="text-align: center; color: var(--text-dim);">Keine Plaene vorhanden</td></tr>
            {% endfor %}
        </tbody>
    </table>
</div>
"""

PLAN_DETAIL_CONTENT = """
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
    .plan-content { background: var(--bg-card); padding: 2rem; border-radius: 8px; }
    .plan-content h1, .plan-content h2, .plan-content h3 { margin-top: 1.5rem; margin-bottom: 0.75rem; }
    .plan-content h1:first-child { margin-top: 0; }
    .plan-content pre { background: var(--bg); padding: 1rem; border-radius: 4px; overflow-x: auto; }
    .plan-content code { font-family: monospace; }
    .plan-content table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
    .plan-content th, .plan-content td { border: 1px solid var(--accent); padding: 0.5rem 0.75rem; text-align: left; }
    .plan-content th { background: var(--accent); }
    .plan-content ul, .plan-content ol { margin-left: 1.5rem; margin-bottom: 1rem; }
    .plan-content blockquote { border-left: 3px solid var(--highlight); padding-left: 1rem; color: var(--text-dim); }
</style>

<div style="margin-bottom: 1rem;">
    <a href="{{ url_for('plans_list') }}" class="btn btn-secondary">Zurueck zur Liste</a>
</div>
<div class="plan-content" id="content"></div>
<script>
    const content = {{ plan_content|tojson }};
    document.getElementById('content').innerHTML = marked.parse(content);
    document.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);
    });
</script>
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

        if user:
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["is_admin"] = user["is_admin"]
            flash("Login erfolgreich", "success")
            return redirect(url_for("home"))
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
@login_required
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
@login_required
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


@app.route("/sessions")
@login_required
def sessions_list():
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)
    with get_db() as conn:
        with conn.cursor() as cur:
            if is_admin:
                # Admins see all sessions with username
                cur.execute("""
                    SELECT s.id, s.project_name, s.started_at, s.total_messages,
                           s.total_tokens_in, s.total_tokens_out, u.username
                    FROM sessions s
                    JOIN users u ON s.user_id = u.id
                    ORDER BY s.started_at DESC
                    LIMIT 100
                """)
            else:
                cur.execute("""
                    SELECT id, project_name, started_at, total_messages,
                           total_tokens_in, total_tokens_out, NULL as username
                    FROM sessions
                    WHERE user_id = %s
                    ORDER BY started_at DESC
                    LIMIT 100
                """, (user_id,))
            sessions_data = cur.fetchall()

    return render_page(SESSIONS_CONTENT, active="sessions", sessions=sessions_data)


@app.route("/replay/<session_id>")
@login_required
def replay(session_id):
    import json
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Check session ownership
            cur.execute("""
                SELECT s.*, u.share_level
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.id = %s AND (s.user_id = %s OR %s = true)
            """, (session_id, user_id, is_admin))
            session_data = cur.fetchone()

            if not session_data:
                flash("Session nicht gefunden", "error")
                return redirect(url_for("sessions_list"))

            share_level = session_data["share_level"]

            # Get messages
            cur.execute("""
                SELECT id, sequence, timestamp, role, content
                FROM messages
                WHERE session_id = %s
                ORDER BY sequence
            """, (session_id,))
            messages = cur.fetchall()

            # Get tool calls
            cur.execute("""
                SELECT message_id, tool_name, tool_input, tool_output, success
                FROM tool_calls
                WHERE session_id = %s
                ORDER BY sequence
            """, (session_id,))
            tool_calls = cur.fetchall()

    messages_list = [dict(m) for m in messages]
    for m in messages_list:
        if m.get("timestamp"):
            m["timestamp"] = m["timestamp"].isoformat()

    tool_calls_list = [dict(tc) for tc in tool_calls]

    return render_page(
        REPLAY_CONTENT,
        active="sessions",
        messages=messages,
        messages_json=json.dumps(messages_list),
        tool_calls_json=json.dumps(tool_calls_list),
        share_level=share_level
    )


@app.route("/tokens")
@login_required
def tokens():
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)
    user_filter = "" if is_admin else "WHERE s.user_id = %s"
    user_params = () if is_admin else (user_id,)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Totals from token_usage table
            cur.execute(f"""
                SELECT
                    COALESCE(SUM(tu.input_tokens), 0) as input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) as output_tokens,
                    COALESCE(SUM(tu.cache_read_tokens), 0) as cache_read,
                    COALESCE(SUM(tu.cache_creation_tokens), 0) as cache_creation
                FROM token_usage tu
                JOIN sessions s ON tu.session_id = s.id
                {user_filter}
            """, user_params)
            totals_row = cur.fetchone()

            # Fallback to sessions table if no token_usage data
            if totals_row["input_tokens"] == 0:
                cur.execute(f"""
                    SELECT
                        COALESCE(SUM(total_tokens_in), 0) as input_tokens,
                        COALESCE(SUM(total_tokens_out), 0) as output_tokens,
                        0 as cache_read,
                        0 as cache_creation
                    FROM sessions s
                    {user_filter}
                """, user_params)
                totals_row = cur.fetchone()

            totals = dict(totals_row)

            # By model
            model_filter = "" if is_admin else "AND s.user_id = %s"
            cur.execute(f"""
                SELECT
                    tu.model,
                    COALESCE(SUM(tu.input_tokens), 0) as input_tokens,
                    COALESCE(SUM(tu.output_tokens), 0) as output_tokens,
                    COALESCE(SUM(tu.cache_read_tokens), 0) as cache_read,
                    COALESCE(SUM(tu.cache_creation_tokens), 0) as cache_creation,
                    COUNT(*) as message_count
                FROM token_usage tu
                JOIN sessions s ON tu.session_id = s.id
                WHERE tu.model IS NOT NULL {model_filter}
                GROUP BY tu.model
                ORDER BY SUM(tu.input_tokens + tu.output_tokens) DESC
            """, user_params)
            by_model = [dict(r) for r in cur.fetchall()]

            # By session
            cur.execute(f"""
                SELECT
                    s.id as session_id,
                    s.project_name,
                    COALESCE(SUM(tu.input_tokens), s.total_tokens_in) as input_tokens,
                    COALESCE(SUM(tu.output_tokens), s.total_tokens_out) as output_tokens
                FROM sessions s
                LEFT JOIN token_usage tu ON tu.session_id = s.id
                {user_filter}
                GROUP BY s.id
                ORDER BY COALESCE(SUM(tu.input_tokens + tu.output_tokens), s.total_tokens_in + s.total_tokens_out) DESC
                LIMIT 20
            """, user_params)
            by_session = [dict(r) for r in cur.fetchall()]

    return render_page(
        TOKENS_CONTENT,
        active="tokens",
        totals=totals,
        by_model=by_model,
        by_session=by_session
    )


@app.route("/search")
@login_required
def search():
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)
    query = request.args.get("q", "").strip()
    results = []

    if query:
        with get_db() as conn:
            with conn.cursor() as cur:
                # Use PostgreSQL FTS with ts_headline for snippets
                if is_admin:
                    cur.execute("""
                        SELECT
                            m.content,
                            m.timestamp,
                            s.project_name,
                            s.id as session_id,
                            u.username,
                            ts_headline('german', m.content, plainto_tsquery('german', %s),
                                       'MaxWords=50, MinWords=25, StartSel=<mark style="background:#e94560;color:#fff">, StopSel=</mark>') as snippet
                        FROM messages m
                        JOIN sessions s ON m.session_id = s.id
                        JOIN users u ON s.user_id = u.id
                        WHERE m.search_vector @@ plainto_tsquery('german', %s)
                        ORDER BY ts_rank(m.search_vector, plainto_tsquery('german', %s)) DESC
                        LIMIT 100
                    """, (query, query, query))
                else:
                    cur.execute("""
                        SELECT
                            m.content,
                            m.timestamp,
                            s.project_name,
                            s.id as session_id,
                            NULL as username,
                            ts_headline('german', m.content, plainto_tsquery('german', %s),
                                       'MaxWords=50, MinWords=25, StartSel=<mark style="background:#e94560;color:#fff">, StopSel=</mark>') as snippet
                        FROM messages m
                        JOIN sessions s ON m.session_id = s.id
                        WHERE s.user_id = %s
                          AND m.search_vector @@ plainto_tsquery('german', %s)
                        ORDER BY ts_rank(m.search_vector, plainto_tsquery('german', %s)) DESC
                        LIMIT 100
                    """, (query, user_id, query, query))
                results = cur.fetchall()

    return render_page(SEARCH_CONTENT, active="search", query=query, results=results)


@app.route("/plans")
@login_required
def plans_list():
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)

    with get_db() as conn:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute("""
                    SELECT p.name, p.title, p.created_at, u.username
                    FROM plans p
                    JOIN users u ON p.user_id = u.id
                    ORDER BY p.created_at DESC
                """)
            else:
                cur.execute("""
                    SELECT name, title, created_at, NULL as username
                    FROM plans
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                """, (user_id,))
            plans = cur.fetchall()

    return render_page(PLANS_CONTENT, active="plans", plans=plans)


@app.route("/plans/<name>")
@login_required
def plan_detail(name):
    user_id = session.get("user_id")
    is_admin = session.get("is_admin", False)

    with get_db() as conn:
        with conn.cursor() as cur:
            if is_admin:
                cur.execute("""
                    SELECT name, title, content
                    FROM plans
                    WHERE name = %s
                """, (name,))
            else:
                cur.execute("""
                    SELECT name, title, content
                    FROM plans
                    WHERE user_id = %s AND name = %s
                """, (user_id, name))
            plan = cur.fetchone()

    if not plan:
        flash("Plan nicht gefunden", "error")
        return redirect(url_for("plans_list"))

    return render_page(
        PLAN_DETAIL_CONTENT,
        active="plans",
        plan=plan,
        plan_content=plan["content"] or ""
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)
