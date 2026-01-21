#!/usr/bin/env python3
"""
Claude Code Session Replay UI

A lightweight web interface for stepping through Claude Code sessions,
with syntax highlighting and timeline navigation.
"""

import os
import json
import sqlite3
import re
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)
DB_PATH = os.environ.get('DB_PATH', '/data/sessions.db')

# HTML Templates
INDEX_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Claude Code Insights - Replay</title>
    <style>
        * { box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 0;
            background: #f5f5f5;
            color: #333;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: #1a1a2e;
            color: white;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        header h1 {
            margin: 0;
            font-weight: 300;
        }
        
        header nav {
            margin-top: 10px;
        }
        
        header nav a {
            color: #90caf9;
            margin-right: 20px;
            text-decoration: none;
        }

        header nav a:hover {
            color: #fff;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }
        
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .stat-card h3 {
            margin: 0 0 8px 0;
            color: #666;
            font-size: 0.9em;
            font-weight: 500;
        }
        
        .stat-card .value {
            font-size: 2em;
            font-weight: 300;
            color: #1a1a2e;
        }
        
        .session-list {
            background: white;
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .session-list h2 {
            padding: 16px 20px;
            margin: 0;
            border-bottom: 1px solid #eee;
            font-weight: 500;
        }
        
        .session-item {
            padding: 16px 20px;
            border-bottom: 1px solid #eee;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        
        .session-item:hover {
            background: #fafafa;
        }
        
        .session-item:last-child {
            border-bottom: none;
        }
        
        .session-info h4 {
            margin: 0 0 4px 0;
            font-weight: 500;
        }
        
        .session-info .meta {
            color: #666;
            font-size: 0.9em;
        }
        
        .session-tags {
            display: flex;
            gap: 4px;
            flex-wrap: wrap;
        }
        
        .tag {
            background: #e3f2fd;
            color: #1565c0;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
        }
        
        .tag.tool {
            background: #fff3e0;
            color: #e65100;
        }
        
        .btn {
            display: inline-block;
            padding: 8px 16px;
            background: #1a1a2e;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-size: 0.9em;
        }
        
        .btn:hover {
            background: #2d2d44;
        }
        
        .search-box {
            padding: 16px 20px;
            border-bottom: 1px solid #eee;
        }
        
        .search-box input {
            width: 100%;
            padding: 10px 14px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 1em;
        }
        
        .empty-state {
            text-align: center;
            padding: 60px 20px;
            color: #666;
        }
        
        .empty-state h3 {
            margin-bottom: 8px;
        }
    </style>
</head>
<body>
    <header>
        <div class="container">
            <h1>Claude Code Insights</h1>
            <nav>
                <a href="/">Dashboard</a>
                <a href="/tokens">Tokens</a>
                <a href="/search">Search</a>
                <a href="/plans">Plans</a>
                <a href="http://localhost:8001" target="_blank">Datasette</a>
            </nav>
        </div>
    </header>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Sessions</h3>
                <div class="value">{{ stats.total_sessions }}</div>
            </div>
            <div class="stat-card">
                <h3>Total Messages</h3>
                <div class="value">{{ stats.total_messages }}</div>
            </div>
            <div class="stat-card">
                <h3>Tool Calls</h3>
                <div class="value">{{ stats.total_tool_calls }}</div>
            </div>
            <div class="stat-card">
                <h3>Unique Tools</h3>
                <div class="value">{{ stats.unique_tools }}</div>
            </div>
            <div class="stat-card">
                <h3>Input Tokens</h3>
                <div class="value">{{ "{:,}".format(stats.total_input_tokens) }}</div>
            </div>
            <div class="stat-card">
                <h3>Output Tokens</h3>
                <div class="value">{{ "{:,}".format(stats.total_output_tokens) }}</div>
            </div>
        </div>
        
        <div class="session-list">
            <h2>Recent Sessions</h2>
            <div class="search-box">
                <input type="text" id="search" placeholder="Search sessions..." onkeyup="filterSessions()">
            </div>
            
            {% if sessions %}
                {% for session in sessions %}
                <div class="session-item" data-search="{{ session.id }} {{ session.project_path or '' }} {{ session.tags or '' }}">
                    <div class="session-info">
                        <h4>{{ session.id[:40] }}{% if session.id|length > 40 %}...{% endif %}</h4>
                        <div class="meta">
                            {% if session.project_path %}
                                📁 {{ session.project_path }} · 
                            {% endif %}
                            {{ session.total_messages }} messages · 
                            {{ session.started_at or 'Unknown date' }}
                        </div>
                        {% if session.tags %}
                        <div class="session-tags" style="margin-top: 8px;">
                            {% for tag in session.tags.split(',') %}
                                <span class="tag {% if tag.startswith('tool:') %}tool{% endif %}">{{ tag }}</span>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                    <a href="/replay/{{ session.id }}" class="btn">Replay →</a>
                </div>
                {% endfor %}
            {% else %}
                <div class="empty-state">
                    <h3>No sessions yet</h3>
                    <p>Sessions will appear here once Claude Code logs are imported.</p>
                </div>
            {% endif %}
        </div>
    </div>
    
    <script>
        function filterSessions() {
            const search = document.getElementById('search').value.toLowerCase();
            document.querySelectorAll('.session-item').forEach(item => {
                const text = item.dataset.search.toLowerCase();
                item.style.display = text.includes(search) ? '' : 'none';
            });
        }
    </script>
</body>
</html>
'''

REPLAY_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Replay: {{ session.id[:30] }}</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github-dark.min.css">
    <style>
        * { box-sizing: border-box; }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 0;
            background: #1a1a2e;
            color: #eee;
            display: flex;
            height: 100vh;
        }
        
        .sidebar {
            width: 300px;
            background: #16162a;
            border-right: 1px solid #2d2d44;
            display: flex;
            flex-direction: column;
            flex-shrink: 0;
        }
        
        .sidebar-header {
            padding: 16px;
            border-bottom: 1px solid #2d2d44;
        }
        
        .sidebar-header h2 {
            margin: 0 0 8px 0;
            font-size: 1em;
            font-weight: 500;
        }
        
        .sidebar-header .meta {
            font-size: 0.85em;
            color: #888;
        }
        
        .sidebar-header a {
            color: #90caf9;
            text-decoration: none;
        }
        
        .timeline {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }
        
        .timeline-item {
            padding: 10px 12px;
            border-radius: 4px;
            margin-bottom: 4px;
            cursor: pointer;
            transition: background 0.2s;
            font-size: 0.9em;
        }
        
        .timeline-item:hover {
            background: #2d2d44;
        }
        
        .timeline-item.active {
            background: #3d3d5c;
        }
        
        .timeline-item.user {
            border-left: 3px solid #42a5f5;
        }
        
        .timeline-item.assistant {
            border-left: 3px solid #66bb6a;
        }
        
        .timeline-item .role {
            font-weight: 500;
            text-transform: uppercase;
            font-size: 0.75em;
            margin-bottom: 4px;
        }
        
        .timeline-item .preview {
            color: #aaa;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .controls {
            padding: 12px 20px;
            background: #16162a;
            border-bottom: 1px solid #2d2d44;
            display: flex;
            align-items: center;
            gap: 12px;
        }
        
        .controls button {
            padding: 8px 16px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            background: #2d2d44;
            color: white;
        }
        
        .controls button:hover {
            background: #3d3d5c;
        }
        
        .controls button.primary {
            background: #42a5f5;
        }
        
        .controls button.primary:hover {
            background: #1e88e5;
        }
        
        .controls .position {
            color: #888;
            font-size: 0.9em;
        }
        
        .controls .speed {
            margin-left: auto;
        }
        
        .message-view {
            flex: 1;
            overflow-y: auto;
            padding: 20px 40px;
        }
        
        .message-container {
            max-width: 900px;
            margin: 0 auto;
        }
        
        .message-header {
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 16px;
        }
        
        .message-header .role {
            font-weight: 600;
            text-transform: uppercase;
            font-size: 0.85em;
            padding: 4px 12px;
            border-radius: 4px;
        }
        
        .message-header .role.user {
            background: #1565c0;
        }
        
        .message-header .role.assistant {
            background: #2e7d32;
        }
        
        .message-header .timestamp {
            color: #666;
            font-size: 0.85em;
        }
        
        .message-body {
            background: #242442;
            border-radius: 8px;
            padding: 20px;
            line-height: 1.7;
            white-space: pre-wrap;
        }
        
        .message-body pre {
            background: #1a1a2e;
            border-radius: 4px;
            padding: 16px;
            overflow-x: auto;
            margin: 16px 0;
        }
        
        .message-body code {
            font-family: 'SF Mono', Monaco, 'Courier New', monospace;
            font-size: 0.9em;
        }
        
        .tool-calls {
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #3d3d5c;
        }
        
        .tool-call {
            background: #2d2d44;
            border-left: 3px solid #ff9800;
            padding: 12px 16px;
            margin: 8px 0;
            border-radius: 0 4px 4px 0;
        }
        
        .tool-call .name {
            font-weight: 600;
            color: #ffb74d;
            margin-bottom: 8px;
        }
        
        .tool-call pre {
            margin: 8px 0 0 0;
            font-size: 0.85em;
        }
        
        .insights-panel {
            background: #16162a;
            border-top: 1px solid #2d2d44;
            padding: 12px 20px;
        }
        
        .insights-panel h4 {
            margin: 0 0 8px 0;
            font-size: 0.85em;
            color: #888;
        }
        
        .insights-tags {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }
        
        .insights-tags .tag {
            background: #2d2d44;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.8em;
        }
        
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .message-body.animate {
            animation: fadeIn 0.3s ease-out;
        }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <h2>Session Timeline</h2>
            <div class="meta">
                {{ messages|length }} messages<br>
                <a href="/">← Back to Dashboard</a>
            </div>
        </div>
        <div class="timeline" id="timeline">
            {% for msg in messages %}
            <div class="timeline-item {{ msg.role }}" data-index="{{ loop.index0 }}" onclick="goTo({{ loop.index0 }})">
                <div class="role">{{ msg.role }}</div>
                <div class="preview">{{ msg.content[:50] }}{% if msg.content|length > 50 %}...{% endif %}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    
    <div class="main-content">
        <div class="controls">
            <button onclick="prev()">← Previous</button>
            <button onclick="togglePlay()" id="playBtn" class="primary">▶ Play</button>
            <button onclick="next()">Next →</button>
            <span class="position" id="position">1 / {{ messages|length }}</span>
            <div class="speed">
                <label>Speed: </label>
                <select id="speed" onchange="updateSpeed()">
                    <option value="3000">Slow</option>
                    <option value="1500" selected>Normal</option>
                    <option value="750">Fast</option>
                </select>
            </div>
        </div>
        
        <div class="message-view">
            <div class="message-container" id="messageContainer">
                <!-- Message content will be injected here -->
            </div>
        </div>
        
        {% if tags %}
        <div class="insights-panel">
            <h4>Session Tags</h4>
            <div class="insights-tags">
                {% for tag in tags %}
                <span class="tag">{{ tag }}</span>
                {% endfor %}
            </div>
        </div>
        {% endif %}
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
    <script>
        const messages = {{ messages_json|safe }};
        const toolCalls = {{ tool_calls_json|safe }};
        let currentIndex = 0;
        let isPlaying = false;
        let playInterval = null;
        let speed = 1500;
        
        function renderMessage(index) {
            const msg = messages[index];
            const container = document.getElementById('messageContainer');
            
            // Format content with code blocks
            let content = escapeHtml(msg.content);
            content = content.replace(/```(\\w*)\\n([\\s\\S]*?)```/g, (match, lang, code) => {
                return `<pre><code class="language-${lang || 'plaintext'}">${code}</code></pre>`;
            });
            content = content.replace(/`([^`]+)`/g, '<code>$1</code>');
            
            // Get tool calls for this message
            const msgTools = toolCalls.filter(tc => tc.message_id === msg.id);
            let toolsHtml = '';
            if (msgTools.length > 0) {
                toolsHtml = '<div class="tool-calls"><h4>Tool Calls</h4>';
                for (const tc of msgTools) {
                    toolsHtml += `
                        <div class="tool-call">
                            <div class="name">🔧 ${escapeHtml(tc.tool_name)}</div>
                            ${tc.tool_input ? `<pre>${escapeHtml(tc.tool_input)}</pre>` : ''}
                        </div>
                    `;
                }
                toolsHtml += '</div>';
            }
            
            container.innerHTML = `
                <div class="message-header">
                    <span class="role ${msg.role}">${msg.role}</span>
                    ${msg.timestamp ? `<span class="timestamp">${msg.timestamp}</span>` : ''}
                </div>
                <div class="message-body animate">${content}${toolsHtml}</div>
            `;
            
            // Highlight code blocks
            container.querySelectorAll('pre code').forEach(block => {
                hljs.highlightElement(block);
            });
            
            // Update position indicator
            document.getElementById('position').textContent = `${index + 1} / ${messages.length}`;
            
            // Update timeline active state
            document.querySelectorAll('.timeline-item').forEach((item, i) => {
                item.classList.toggle('active', i === index);
            });
            
            // Scroll timeline item into view
            const activeItem = document.querySelector('.timeline-item.active');
            if (activeItem) {
                activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
        
        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
        
        function goTo(index) {
            currentIndex = Math.max(0, Math.min(index, messages.length - 1));
            renderMessage(currentIndex);
        }
        
        function prev() {
            goTo(currentIndex - 1);
        }
        
        function next() {
            goTo(currentIndex + 1);
        }
        
        function togglePlay() {
            isPlaying = !isPlaying;
            const btn = document.getElementById('playBtn');
            
            if (isPlaying) {
                btn.textContent = '⏸ Pause';
                playInterval = setInterval(() => {
                    if (currentIndex < messages.length - 1) {
                        next();
                    } else {
                        togglePlay();
                    }
                }, speed);
            } else {
                btn.textContent = '▶ Play';
                clearInterval(playInterval);
            }
        }
        
        function updateSpeed() {
            speed = parseInt(document.getElementById('speed').value);
            if (isPlaying) {
                clearInterval(playInterval);
                playInterval = setInterval(() => {
                    if (currentIndex < messages.length - 1) {
                        next();
                    } else {
                        togglePlay();
                    }
                }, speed);
            }
        }
        
        // Keyboard navigation
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') prev();
            if (e.key === 'ArrowRight') next();
            if (e.key === ' ') { e.preventDefault(); togglePlay(); }
        });
        
        // Initial render
        renderMessage(0);
    </script>
</body>
</html>
'''


def get_db():
    """Get database connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    """Dashboard with session list and stats."""
    conn = get_db()
    
    # Get stats
    stats = {
        'total_sessions': conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],
        'total_messages': conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0],
        'total_tool_calls': conn.execute('SELECT COUNT(*) FROM tool_calls').fetchone()[0],
        'unique_tools': conn.execute('SELECT COUNT(DISTINCT tool_name) FROM tool_calls WHERE tool_name IS NOT NULL').fetchone()[0],
        'total_input_tokens': conn.execute('SELECT COALESCE(SUM(input_tokens), 0) FROM token_usage').fetchone()[0],
        'total_output_tokens': conn.execute('SELECT COALESCE(SUM(output_tokens), 0) FROM token_usage').fetchone()[0],
    }
    
    # Get recent sessions with tags
    sessions = conn.execute('''
        SELECT 
            s.id,
            s.project_path,
            s.started_at,
            s.total_messages,
            GROUP_CONCAT(DISTINCT t.tag) as tags
        FROM sessions s
        LEFT JOIN session_tags t ON s.id = t.session_id
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT 50
    ''').fetchall()
    
    conn.close()
    
    return render_template_string(INDEX_TEMPLATE, stats=stats, sessions=sessions)


@app.route('/replay/<session_id>')
def replay(session_id):
    """Replay view for a specific session."""
    conn = get_db()
    
    # Get session info
    session = conn.execute(
        'SELECT * FROM sessions WHERE id = ?', 
        (session_id,)
    ).fetchone()
    
    if not session:
        return "Session not found", 404
    
    # Get messages
    messages = conn.execute('''
        SELECT id, sequence, timestamp, role, content
        FROM messages 
        WHERE session_id = ?
        ORDER BY sequence
    ''', (session_id,)).fetchall()
    
    # Get tool calls
    tool_calls = conn.execute('''
        SELECT message_id, tool_name, tool_input, tool_output, success
        FROM tool_calls
        WHERE session_id = ?
    ''', (session_id,)).fetchall()
    
    # Get tags
    tags = conn.execute(
        'SELECT tag FROM session_tags WHERE session_id = ?',
        (session_id,)
    ).fetchall()
    
    conn.close()
    
    # Convert to JSON for JavaScript
    messages_json = json.dumps([dict(m) for m in messages])
    tool_calls_json = json.dumps([dict(tc) for tc in tool_calls])
    tags_list = [t['tag'] for t in tags]
    
    return render_template_string(
        REPLAY_TEMPLATE,
        session=session,
        messages=messages,
        messages_json=messages_json,
        tool_calls_json=tool_calls_json,
        tags=tags_list
    )


@app.route('/api/sessions')
def api_sessions():
    """API endpoint for sessions."""
    conn = get_db()
    sessions = conn.execute('''
        SELECT 
            s.id,
            s.project_path,
            s.started_at,
            s.total_messages,
            GROUP_CONCAT(DISTINCT t.tag) as tags
        FROM sessions s
        LEFT JOIN session_tags t ON s.id = t.session_id
        GROUP BY s.id
        ORDER BY s.started_at DESC
        LIMIT 100
    ''').fetchall()
    conn.close()
    
    return jsonify([dict(s) for s in sessions])


@app.route('/api/sessions/<session_id>/messages')
def api_messages(session_id):
    """API endpoint for session messages."""
    conn = get_db()
    messages = conn.execute('''
        SELECT id, sequence, timestamp, role, content
        FROM messages 
        WHERE session_id = ?
        ORDER BY sequence
    ''', (session_id,)).fetchall()
    conn.close()
    
    return jsonify([dict(m) for m in messages])


SEARCH_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Search Prompts - Claude Code Insights</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #f5f5f5; color: #333; }
        header { background: #1a1a2e; color: white; padding: 20px; }
        header h1 { margin: 0; font-weight: 300; }
        header nav { margin-top: 10px; }
        header nav a { color: #90caf9; margin-right: 20px; text-decoration: none; }
        header nav a:hover { color: #fff; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .search-box { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .search-box input { width: 100%; padding: 12px; font-size: 16px; border: 1px solid #ddd; border-radius: 4px; }
        .results { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .result-item { padding: 16px 20px; border-bottom: 1px solid #eee; }
        .result-item:last-child { border-bottom: none; }
        .result-item .prompt { font-size: 1.1em; margin-bottom: 8px; }
        .result-item .meta { color: #666; font-size: 0.9em; }
        .result-item .project { color: #1a73e8; }
        .highlight { background: #fff3cd; padding: 2px 4px; border-radius: 2px; }
    </style>
</head>
<body>
    <header>
        <h1>Claude Code Insights</h1>
        <nav>
            <a href="/">Dashboard</a>
            <a href="/tokens">Tokens</a>
            <a href="/search">Search</a>
            <a href="/plans">Plans</a>
            <a href="http://localhost:8001" target="_blank">Datasette</a>
        </nav>
    </header>
    <div class="container">
        <div class="search-box">
            <form method="GET" action="/search">
                <input type="text" name="q" placeholder="Search your prompt history..." value="{{ query }}" autofocus>
            </form>
        </div>
        {% if results %}
        <div class="results">
            <p style="padding: 16px 20px; color: #666; margin: 0; border-bottom: 1px solid #eee;">Found {{ results|length }} results</p>
            {% for r in results %}
            <div class="result-item">
                <div class="prompt">{{ r.prompt }}</div>
                <div class="meta">
                    <span class="project">📁 {{ r.project_path or 'Unknown project' }}</span>
                    · {{ r.timestamp or 'Unknown date' }}
                </div>
            </div>
            {% endfor %}
        </div>
        {% elif query %}
        <div class="results">
            <p style="padding: 40px; text-align: center; color: #666;">No results found for "{{ query }}"</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
'''

PLANS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Plans - Claude Code Insights</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #f5f5f5; color: #333; }
        header { background: #1a1a2e; color: white; padding: 20px; }
        header h1 { margin: 0; font-weight: 300; }
        header nav { margin-top: 10px; }
        header nav a { color: #90caf9; margin-right: 20px; text-decoration: none; }
        header nav a:hover { color: #fff; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .plans-list { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .plans-list h2 { padding: 16px 20px; margin: 0; border-bottom: 1px solid #eee; }
        .plan-item { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #eee; }
        .plan-item:last-child { border-bottom: none; }
        .plan-item h4 { margin: 0 0 4px 0; }
        .plan-item .meta { color: #666; font-size: 0.9em; }
        .plan-item a { color: #1a73e8; text-decoration: none; }
        .plan-item a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <header>
        <h1>Claude Code Insights</h1>
        <nav>
            <a href="/">Dashboard</a>
            <a href="/tokens">Tokens</a>
            <a href="/search">Search</a>
            <a href="/plans">Plans</a>
            <a href="http://localhost:8001" target="_blank">Datasette</a>
        </nav>
    </header>
    <div class="container">
        <div class="plans-list">
            <h2>Implementation Plans ({{ plans|length }})</h2>
            {% for p in plans %}
            <div class="plan-item">
                <div>
                    <h4>{{ p.title }}</h4>
                    <div class="meta">{{ p.name }} · {{ p.created_at }}</div>
                </div>
                <a href="/plans/{{ p.name }}">View →</a>
            </div>
            {% endfor %}
        </div>
    </div>
</body>
</html>
'''

PLAN_DETAIL_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ plan.title }} - Claude Code Insights</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/styles/github.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.8.0/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #f5f5f5; color: #333; }
        header { background: #1a1a2e; color: white; padding: 20px; }
        header h1 { margin: 0; font-weight: 300; }
        header nav { margin-top: 10px; }
        header nav a { color: #90caf9; margin-right: 20px; text-decoration: none; }
        header nav a:hover { color: #fff; }
        .container { max-width: 900px; margin: 0 auto; padding: 20px; }
        .plan-content { background: white; border-radius: 8px; padding: 30px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .plan-content h1, .plan-content h2, .plan-content h3 { color: #1a1a2e; }
        .plan-content pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; }
        .plan-content code { font-family: 'SF Mono', Consolas, monospace; font-size: 0.9em; }
        .plan-content table { border-collapse: collapse; width: 100%; margin: 16px 0; }
        .plan-content th, .plan-content td { border: 1px solid #ddd; padding: 8px 12px; text-align: left; }
        .plan-content th { background: #f6f8fa; }
        .back-link { margin-bottom: 16px; }
        .back-link a { color: #1a73e8; text-decoration: none; }
    </style>
</head>
<body>
    <header>
        <h1>Claude Code Insights</h1>
        <nav>
            <a href="/">Dashboard</a>
            <a href="/tokens">Tokens</a>
            <a href="/search">Search</a>
            <a href="/plans">Plans</a>
            <a href="http://localhost:8001" target="_blank">Datasette</a>
        </nav>
    </header>
    <div class="container">
        <div class="back-link"><a href="/plans">← Back to Plans</a></div>
        <div class="plan-content" id="content"></div>
    </div>
    <script>
        const content = {{ plan_content|tojson }};
        document.getElementById('content').innerHTML = marked.parse(content);
        document.querySelectorAll('pre code').forEach((block) => {
            hljs.highlightElement(block);
        });
    </script>
</body>
</html>
'''


@app.route('/search')
def search():
    """Search prompt history."""
    query = request.args.get('q', '').strip()
    results = []

    if query:
        conn = get_db()
        # Use FTS for search
        results = conn.execute('''
            SELECT ph.prompt, ph.project_path, ph.timestamp
            FROM prompt_history_fts fts
            JOIN prompt_history ph ON fts.rowid = ph.id
            WHERE fts.prompt MATCH ?
            ORDER BY ph.timestamp_ms DESC
            LIMIT 100
        ''', (query,)).fetchall()
        conn.close()

    return render_template_string(SEARCH_TEMPLATE, query=query, results=results)


@app.route('/plans')
def plans_list():
    """List all implementation plans."""
    conn = get_db()
    plans = conn.execute('''
        SELECT name, title, created_at
        FROM plans
        ORDER BY created_at DESC
    ''').fetchall()
    conn.close()

    return render_template_string(PLANS_TEMPLATE, plans=plans)


@app.route('/plans/<name>')
def plan_detail(name):
    """View a specific plan."""
    conn = get_db()
    plan = conn.execute(
        'SELECT name, title, content FROM plans WHERE name = ?',
        (name,)
    ).fetchone()
    conn.close()

    if not plan:
        return "Plan not found", 404

    return render_template_string(
        PLAN_DETAIL_TEMPLATE,
        plan=plan,
        plan_content=plan['content']
    )


@app.route('/api/search')
def api_search():
    """API endpoint for searching prompts."""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify([])

    conn = get_db()
    results = conn.execute('''
        SELECT ph.prompt, ph.project_path, ph.timestamp
        FROM prompt_history_fts fts
        JOIN prompt_history ph ON fts.rowid = ph.id
        WHERE fts.prompt MATCH ?
        ORDER BY ph.timestamp_ms DESC
        LIMIT 100
    ''', (query,)).fetchall()
    conn.close()

    return jsonify([dict(r) for r in results])


@app.route('/api/stats')
def api_stats():
    """API endpoint for usage statistics."""
    conn = get_db()
    stats = conn.execute('''
        SELECT model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens
        FROM usage_stats
    ''').fetchall()
    conn.close()

    return jsonify([dict(s) for s in stats])


TOKENS_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Token Usage - Claude Code Insights</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; background: #f5f5f5; color: #333; }
        header { background: #1a1a2e; color: white; padding: 20px; }
        header h1 { margin: 0; font-weight: 300; }
        header nav { margin-top: 10px; }
        header nav a { color: #90caf9; margin-right: 20px; text-decoration: none; }
        header nav a:hover { color: #fff; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .stat-card h3 { margin: 0 0 8px 0; color: #666; font-size: 0.9em; }
        .stat-card .value { font-size: 2em; font-weight: 300; color: #1a1a2e; }
        .stat-card .sub { font-size: 0.85em; color: #888; margin-top: 4px; }
        .data-table { background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); overflow: hidden; margin-bottom: 24px; }
        .data-table h2 { padding: 16px 20px; margin: 0; border-bottom: 1px solid #eee; font-weight: 500; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 12px 20px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #fafafa; font-weight: 500; color: #666; }
        tr:last-child td { border-bottom: none; }
        .number { text-align: right; font-variant-numeric: tabular-nums; }
        .model-name { font-family: monospace; background: #f0f0f0; padding: 2px 8px; border-radius: 4px; }
    </style>
</head>
<body>
    <header>
        <h1>Claude Code Insights</h1>
        <nav>
            <a href="/">Dashboard</a>
            <a href="/tokens">Tokens</a>
            <a href="/search">Search</a>
            <a href="/plans">Plans</a>
            <a href="http://localhost:8001" target="_blank">Datasette</a>
        </nav>
    </header>
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Input Tokens</h3>
                <div class="value">{{ "{:,}".format(totals.input_tokens) }}</div>
            </div>
            <div class="stat-card">
                <h3>Total Output Tokens</h3>
                <div class="value">{{ "{:,}".format(totals.output_tokens) }}</div>
            </div>
            <div class="stat-card">
                <h3>Cache Read Tokens</h3>
                <div class="value">{{ "{:,}".format(totals.cache_read) }}</div>
            </div>
            <div class="stat-card">
                <h3>Cache Creation Tokens</h3>
                <div class="value">{{ "{:,}".format(totals.cache_creation) }}</div>
            </div>
        </div>

        <div class="data-table">
            <h2>Token Usage by Model</h2>
            <table>
                <thead>
                    <tr>
                        <th>Model</th>
                        <th class="number">Input Tokens</th>
                        <th class="number">Output Tokens</th>
                        <th class="number">Cache Read</th>
                        <th class="number">Cache Creation</th>
                        <th class="number">Messages</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in by_model %}
                    <tr>
                        <td><span class="model-name">{{ row.model }}</span></td>
                        <td class="number">{{ "{:,}".format(row.input_tokens) }}</td>
                        <td class="number">{{ "{:,}".format(row.output_tokens) }}</td>
                        <td class="number">{{ "{:,}".format(row.cache_read) }}</td>
                        <td class="number">{{ "{:,}".format(row.cache_creation) }}</td>
                        <td class="number">{{ "{:,}".format(row.message_count) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="data-table">
            <h2>Recent Sessions by Token Usage</h2>
            <table>
                <thead>
                    <tr>
                        <th>Session</th>
                        <th class="number">Input</th>
                        <th class="number">Output</th>
                        <th class="number">Total</th>
                    </tr>
                </thead>
                <tbody>
                    {% for row in by_session %}
                    <tr>
                        <td><a href="/replay/{{ row.session_id }}">{{ row.session_id[:30] }}...</a></td>
                        <td class="number">{{ "{:,}".format(row.input_tokens) }}</td>
                        <td class="number">{{ "{:,}".format(row.output_tokens) }}</td>
                        <td class="number">{{ "{:,}".format(row.input_tokens + row.output_tokens) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
'''


@app.route('/tokens')
def tokens():
    """Token usage statistics page."""
    conn = get_db()

    # Get totals
    totals_row = conn.execute('''
        SELECT
            COALESCE(SUM(input_tokens), 0) as input_tokens,
            COALESCE(SUM(output_tokens), 0) as output_tokens,
            COALESCE(SUM(cache_read_tokens), 0) as cache_read,
            COALESCE(SUM(cache_creation_tokens), 0) as cache_creation
        FROM token_usage
    ''').fetchone()

    totals = {
        'input_tokens': totals_row[0],
        'output_tokens': totals_row[1],
        'cache_read': totals_row[2],
        'cache_creation': totals_row[3]
    }

    # Get by model
    by_model = conn.execute('''
        SELECT
            model,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens,
            SUM(cache_read_tokens) as cache_read,
            SUM(cache_creation_tokens) as cache_creation,
            COUNT(*) as message_count
        FROM token_usage
        WHERE model IS NOT NULL
        GROUP BY model
        ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC
    ''').fetchall()

    # Get by session (top 20)
    by_session = conn.execute('''
        SELECT
            session_id,
            SUM(input_tokens) as input_tokens,
            SUM(output_tokens) as output_tokens
        FROM token_usage
        GROUP BY session_id
        ORDER BY SUM(input_tokens) + SUM(output_tokens) DESC
        LIMIT 20
    ''').fetchall()

    conn.close()

    return render_template_string(
        TOKENS_TEMPLATE,
        totals=totals,
        by_model=[dict(r) for r in by_model],
        by_session=[dict(r) for r in by_session]
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8002, debug=False)
