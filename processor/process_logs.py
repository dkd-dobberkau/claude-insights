#!/usr/bin/env python3
"""
Claude Code Log Processor

Watches Claude Code log directories and imports session data into SQLite
for analysis and replay functionality.
"""

import json
import sqlite3
import hashlib
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LogProcessor:
    def __init__(self, db_path: str, log_path: str):
        self.db_path = Path(db_path)
        self.log_path = Path(log_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database with required tables."""
        conn = sqlite3.connect(self.db_path)
        conn.executescript('''
            -- Sessions table: one row per Claude Code session
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                project_path TEXT,
                started_at TEXT,
                ended_at TEXT,
                total_messages INTEGER DEFAULT 0,
                total_tokens_in INTEGER DEFAULT 0,
                total_tokens_out INTEGER DEFAULT 0,
                file_hash TEXT,
                imported_at TEXT,
                raw_metadata TEXT
            );

            -- Messages table: individual interactions within a session
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                timestamp TEXT,
                role TEXT NOT NULL,
                content TEXT,
                content_type TEXT DEFAULT 'text',
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Tool calls made during sessions
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_id INTEGER,
                sequence INTEGER,
                tool_name TEXT NOT NULL,
                tool_input TEXT,
                tool_output TEXT,
                duration_ms INTEGER,
                success INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id),
                FOREIGN KEY (message_id) REFERENCES messages(id)
            );

            -- File changes tracked during sessions
            CREATE TABLE IF NOT EXISTS file_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_id INTEGER,
                file_path TEXT NOT NULL,
                change_type TEXT,
                diff_summary TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Tags for categorizing sessions
            CREATE TABLE IF NOT EXISTS session_tags (
                session_id TEXT NOT NULL,
                tag TEXT NOT NULL,
                auto_generated INTEGER DEFAULT 0,
                PRIMARY KEY (session_id, tag),
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Insights derived from analysis
            CREATE TABLE IF NOT EXISTS insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                insight_type TEXT NOT NULL,
                insight_key TEXT,
                insight_value TEXT,
                created_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Prompt history for global search
            CREATE TABLE IF NOT EXISTS prompt_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt TEXT NOT NULL,
                project_path TEXT,
                timestamp TEXT,
                timestamp_ms INTEGER
            );

            -- Usage statistics
            CREATE TABLE IF NOT EXISTS usage_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_date TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                updated_at TEXT
            );

            -- Implementation plans
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                title TEXT,
                content TEXT,
                created_at TEXT,
                file_hash TEXT
            );

            -- Session todos
            CREATE TABLE IF NOT EXISTS session_todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                content TEXT,
                status TEXT,
                sequence INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Token usage per message
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                message_sequence INTEGER,
                timestamp TEXT,
                model TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cache_read_tokens INTEGER DEFAULT 0,
                cache_creation_tokens INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            -- Create indexes for common queries
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            CREATE INDEX IF NOT EXISTS idx_messages_role ON messages(role);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_session ON tool_calls(session_id);
            CREATE INDEX IF NOT EXISTS idx_tool_calls_name ON tool_calls(tool_name);
            CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
            CREATE INDEX IF NOT EXISTS idx_file_changes_path ON file_changes(file_path);
            CREATE INDEX IF NOT EXISTS idx_prompt_history_project ON prompt_history(project_path);
            CREATE INDEX IF NOT EXISTS idx_prompt_history_timestamp ON prompt_history(timestamp_ms);
            CREATE INDEX IF NOT EXISTS idx_token_usage_session ON token_usage(session_id);
            CREATE INDEX IF NOT EXISTS idx_token_usage_model ON token_usage(model);

            -- Full-text search on message content
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                content='messages',
                content_rowid='id'
            );

            -- Full-text search on prompt history
            CREATE VIRTUAL TABLE IF NOT EXISTS prompt_history_fts USING fts5(
                prompt,
                content='prompt_history',
                content_rowid='id'
            );

            -- Triggers to keep prompt_history FTS in sync
            CREATE TRIGGER IF NOT EXISTS prompt_history_ai AFTER INSERT ON prompt_history BEGIN
                INSERT INTO prompt_history_fts(rowid, prompt) VALUES (new.id, new.prompt);
            END;

            -- Triggers to keep FTS in sync
            CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content) 
                VALUES('delete', old.id, old.content);
            END;

            CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
                INSERT INTO messages_fts(messages_fts, rowid, content) 
                VALUES('delete', old.id, old.content);
                INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
            END;
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")

    def _file_hash(self, filepath: Path) -> str:
        """Calculate MD5 hash of a file for change detection."""
        return hashlib.md5(filepath.read_bytes()).hexdigest()

    def _is_processed(self, filepath: Path) -> bool:
        """Check if a log file has already been processed."""
        file_hash = self._file_hash(filepath)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT 1 FROM sessions WHERE file_hash = ?", 
            (file_hash,)
        )
        result = cursor.fetchone() is not None
        conn.close()
        return result

    def _parse_claude_code_log(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """
        Parse a Claude Code log file.
        
        Claude Code stores logs in various formats depending on version.
        This handles the common structures.
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Try parsing as JSON
            try:
                data = json.loads(content)
                return self._normalize_json_log(data, filepath)
            except json.JSONDecodeError:
                pass
            
            # Try parsing as JSONL (one JSON object per line)
            lines = content.strip().split('\n')
            if all(self._is_json_line(line) for line in lines if line.strip()):
                return self._normalize_jsonl_log(lines, filepath)
            
            # Try parsing as markdown/text transcript
            return self._normalize_text_log(content, filepath)
            
        except Exception as e:
            logger.error(f"Error parsing {filepath}: {e}")
            return None

    def _is_json_line(self, line: str) -> bool:
        """Check if a line is valid JSON."""
        try:
            json.loads(line)
            return True
        except:
            return False

    def _normalize_json_log(self, data: Dict, filepath: Path) -> Dict[str, Any]:
        """Normalize a JSON-format log into our standard structure."""
        session_id = data.get('sessionId') or data.get('id') or filepath.stem
        
        messages = []
        tool_calls = []
        
        # Handle different message formats
        raw_messages = data.get('messages', data.get('conversation', []))
        
        for idx, msg in enumerate(raw_messages):
            normalized_msg = {
                'sequence': idx,
                'timestamp': msg.get('timestamp', msg.get('ts')),
                'role': msg.get('role', 'unknown'),
                'content': self._extract_content(msg),
                'content_type': 'text'
            }
            messages.append(normalized_msg)
            
            # Extract tool calls from assistant messages
            if msg.get('role') == 'assistant':
                for tc in msg.get('tool_calls', msg.get('toolCalls', [])):
                    tool_calls.append({
                        'message_sequence': idx,
                        'tool_name': tc.get('name', tc.get('function', {}).get('name')),
                        'tool_input': json.dumps(tc.get('input', tc.get('arguments', {}))),
                        'tool_output': tc.get('output', tc.get('result')),
                        'success': tc.get('success', True)
                    })
        
        return {
            'session_id': session_id,
            'project_path': data.get('cwd', data.get('projectPath')),
            'started_at': data.get('startedAt', data.get('timestamp')),
            'ended_at': data.get('endedAt'),
            'messages': messages,
            'tool_calls': tool_calls,
            'tokens_in': data.get('tokensIn', data.get('usage', {}).get('input_tokens', 0)),
            'tokens_out': data.get('tokensOut', data.get('usage', {}).get('output_tokens', 0)),
            'metadata': data
        }

    def _normalize_jsonl_log(self, lines: List[str], filepath: Path) -> Dict[str, Any]:
        """Normalize a JSONL-format log into our standard structure."""
        session_id = filepath.stem
        messages = []
        tool_calls = []
        token_usage = []
        first_ts = None
        last_ts = None
        total_input_tokens = 0
        total_output_tokens = 0

        # Extract project path from parent directory name (e.g., -Users-olivier-project -> /Users/olivier/project)
        project_path = None
        parent_name = filepath.parent.name
        if parent_name.startswith('-'):
            project_path = parent_name.replace('-', '/')

        for idx, line in enumerate(lines):
            if not line.strip():
                continue
            entry = json.loads(line)

            ts = entry.get('timestamp', entry.get('ts'))
            if ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts

            entry_type = entry.get('type')

            # Handle Claude Code format: type is 'user' or 'assistant'
            # Content is nested in entry.message.content
            if entry_type in ('user', 'assistant'):
                msg_data = entry.get('message', entry)
                msg_sequence = len(messages)
                messages.append({
                    'sequence': msg_sequence,
                    'timestamp': ts,
                    'role': entry_type,
                    'content': self._extract_content(msg_data),
                    'content_type': 'text'
                })

                # Extract token usage from assistant messages
                if entry_type == 'assistant':
                    usage = msg_data.get('usage', {})
                    if usage:
                        input_tokens = usage.get('input_tokens', 0)
                        output_tokens = usage.get('output_tokens', 0)
                        cache_read = usage.get('cache_read_input_tokens', 0)
                        cache_creation = usage.get('cache_creation_input_tokens', 0)

                        total_input_tokens += input_tokens
                        total_output_tokens += output_tokens

                        token_usage.append({
                            'message_sequence': msg_sequence,
                            'timestamp': ts,
                            'model': msg_data.get('model', 'unknown'),
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens,
                            'cache_read_tokens': cache_read,
                            'cache_creation_tokens': cache_creation
                        })

                    # Extract tool_use blocks from assistant messages
                    content = msg_data.get('content', [])
                    if isinstance(content, list):
                        for block in content:
                            if isinstance(block, dict) and block.get('type') == 'tool_use':
                                tool_calls.append({
                                    'message_sequence': msg_sequence,
                                    'tool_name': block.get('name'),
                                    'tool_input': json.dumps(block.get('input', {})),
                                    'tool_output': None,
                                    'success': True
                                })
            # Handle legacy format with 'role' field
            elif entry_type == 'message' or 'role' in entry:
                messages.append({
                    'sequence': len(messages),
                    'timestamp': ts,
                    'role': entry.get('role', 'unknown'),
                    'content': self._extract_content(entry),
                    'content_type': 'text'
                })
            elif entry_type == 'tool_call':
                tool_calls.append({
                    'message_sequence': len(messages) - 1,
                    'tool_name': entry.get('name'),
                    'tool_input': json.dumps(entry.get('input', {})),
                    'tool_output': entry.get('output'),
                    'success': entry.get('success', True)
                })

        # Use file modification time as fallback for timestamps
        if not first_ts:
            mtime = filepath.stat().st_mtime
            first_ts = datetime.fromtimestamp(mtime).isoformat()
            last_ts = first_ts

        return {
            'session_id': session_id,
            'project_path': project_path,
            'started_at': first_ts,
            'ended_at': last_ts,
            'messages': messages,
            'tool_calls': tool_calls,
            'token_usage': token_usage,
            'tokens_in': total_input_tokens,
            'tokens_out': total_output_tokens,
            'metadata': {'source': 'jsonl', 'line_count': len(lines)}
        }

    def _normalize_text_log(self, content: str, filepath: Path) -> Dict[str, Any]:
        """Normalize a text/markdown transcript into our standard structure."""
        session_id = filepath.stem
        messages = []
        
        # Simple heuristic: look for role markers
        current_role = None
        current_content = []
        
        for line in content.split('\n'):
            line_lower = line.lower().strip()
            
            # Detect role changes
            if line_lower.startswith('human:') or line_lower.startswith('user:'):
                if current_role and current_content:
                    messages.append({
                        'sequence': len(messages),
                        'timestamp': None,
                        'role': current_role,
                        'content': '\n'.join(current_content).strip(),
                        'content_type': 'text'
                    })
                current_role = 'user'
                current_content = [line.split(':', 1)[1] if ':' in line else '']
            elif line_lower.startswith('assistant:') or line_lower.startswith('claude:'):
                if current_role and current_content:
                    messages.append({
                        'sequence': len(messages),
                        'timestamp': None,
                        'role': current_role,
                        'content': '\n'.join(current_content).strip(),
                        'content_type': 'text'
                    })
                current_role = 'assistant'
                current_content = [line.split(':', 1)[1] if ':' in line else '']
            else:
                current_content.append(line)
        
        # Don't forget the last message
        if current_role and current_content:
            messages.append({
                'sequence': len(messages),
                'timestamp': None,
                'role': current_role,
                'content': '\n'.join(current_content).strip(),
                'content_type': 'text'
            })
        
        return {
            'session_id': session_id,
            'project_path': None,
            'started_at': None,
            'ended_at': None,
            'messages': messages,
            'tool_calls': [],
            'tokens_in': 0,
            'tokens_out': 0,
            'metadata': {'source': 'text'}
        }

    def _extract_content(self, msg: Dict) -> str:
        """Extract text content from various message formats."""
        content = msg.get('content', '')

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # Handle content blocks (text, images, tool_use, tool_result, etc.)
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    block_type = block.get('type')
                    if block_type == 'text':
                        parts.append(block.get('text', ''))
                    elif block_type == 'tool_use':
                        parts.append(f"[Tool: {block.get('name')}]")
                    elif block_type == 'tool_result':
                        # Tool result content can be string or nested
                        result_content = block.get('content', '')
                        if isinstance(result_content, str):
                            # Truncate long tool results
                            if len(result_content) > 500:
                                result_content = result_content[:500] + '...'
                            parts.append(f"[Tool Result: {result_content}]")
                        elif isinstance(result_content, list):
                            # Handle nested content in tool results
                            for item in result_content:
                                if isinstance(item, dict) and item.get('type') == 'text':
                                    parts.append(f"[Tool Result: {item.get('text', '')[:500]}]")
            return '\n'.join(parts)

        return str(content)

    def _import_session(self, parsed: Dict[str, Any], file_hash: str):
        """Import a parsed session into the database."""
        conn = sqlite3.connect(self.db_path)
        
        try:
            # Insert session
            conn.execute('''
                INSERT OR REPLACE INTO sessions 
                (id, project_path, started_at, ended_at, total_messages,
                 total_tokens_in, total_tokens_out, file_hash, imported_at, raw_metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                parsed['session_id'],
                parsed.get('project_path'),
                parsed.get('started_at'),
                parsed.get('ended_at'),
                len(parsed.get('messages', [])),
                parsed.get('tokens_in', 0),
                parsed.get('tokens_out', 0),
                file_hash,
                datetime.now().isoformat(),
                json.dumps(parsed.get('metadata', {}))
            ))
            
            # Insert messages
            for msg in parsed.get('messages', []):
                cursor = conn.execute('''
                    INSERT INTO messages 
                    (session_id, sequence, timestamp, role, content, content_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    parsed['session_id'],
                    msg['sequence'],
                    msg.get('timestamp'),
                    msg['role'],
                    msg['content'],
                    msg.get('content_type', 'text')
                ))
                message_id = cursor.lastrowid
                
                # Link tool calls to this message
                for tc in parsed.get('tool_calls', []):
                    if tc.get('message_sequence') == msg['sequence']:
                        conn.execute('''
                            INSERT INTO tool_calls
                            (session_id, message_id, sequence, tool_name, 
                             tool_input, tool_output, success)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            parsed['session_id'],
                            message_id,
                            tc.get('message_sequence'),
                            tc['tool_name'],
                            tc.get('tool_input'),
                            tc.get('tool_output'),
                            tc.get('success', 1)
                        ))
            
            # Import token usage
            for tu in parsed.get('token_usage', []):
                conn.execute('''
                    INSERT INTO token_usage
                    (session_id, message_sequence, timestamp, model,
                     input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    parsed['session_id'],
                    tu.get('message_sequence'),
                    tu.get('timestamp'),
                    tu.get('model'),
                    tu.get('input_tokens', 0),
                    tu.get('output_tokens', 0),
                    tu.get('cache_read_tokens', 0),
                    tu.get('cache_creation_tokens', 0)
                ))

            # Auto-generate tags based on content
            self._generate_tags(conn, parsed)

            conn.commit()
            tokens_in = parsed.get('tokens_in', 0)
            tokens_out = parsed.get('tokens_out', 0)
            logger.info(f"Imported session {parsed['session_id']} with {len(parsed.get('messages', []))} messages, {tokens_in:,} in / {tokens_out:,} out tokens")
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error importing session: {e}")
            raise
        finally:
            conn.close()

    def _generate_tags(self, conn: sqlite3.Connection, parsed: Dict):
        """Auto-generate tags based on session content."""
        tags = set()
        
        # Tag by tool usage
        tool_names = {tc['tool_name'] for tc in parsed.get('tool_calls', [])}
        for tool in tool_names:
            if tool:
                tags.add(f"tool:{tool}")
        
        # Tag by content patterns
        all_content = ' '.join(
            msg.get('content', '') for msg in parsed.get('messages', [])
        ).lower()
        
        patterns = {
            'debugging': ['error', 'bug', 'fix', 'debug', 'issue'],
            'refactoring': ['refactor', 'cleanup', 'restructure'],
            'feature': ['implement', 'add feature', 'new feature'],
            'testing': ['test', 'spec', 'coverage'],
            'documentation': ['document', 'readme', 'comment'],
        }
        
        for tag, keywords in patterns.items():
            if any(kw in all_content for kw in keywords):
                tags.add(tag)
        
        # Insert tags
        for tag in tags:
            conn.execute('''
                INSERT OR IGNORE INTO session_tags (session_id, tag, auto_generated)
                VALUES (?, ?, 1)
            ''', (parsed['session_id'], tag))

    def _import_prompt_history(self):
        """Import prompt history from history.jsonl for global search."""
        history_file = self.log_path / 'history.jsonl'
        if not history_file.exists():
            return

        conn = sqlite3.connect(self.db_path)
        try:
            # Get existing max timestamp to only import new entries
            cursor = conn.execute("SELECT MAX(timestamp_ms) FROM prompt_history")
            last_ts = cursor.fetchone()[0] or 0

            imported = 0
            with open(history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        ts_ms = entry.get('timestamp', 0)
                        if ts_ms > last_ts:
                            ts_iso = datetime.fromtimestamp(ts_ms / 1000).isoformat() if ts_ms else None
                            conn.execute('''
                                INSERT INTO prompt_history (prompt, project_path, timestamp, timestamp_ms)
                                VALUES (?, ?, ?, ?)
                            ''', (
                                entry.get('display', ''),
                                entry.get('project'),
                                ts_iso,
                                ts_ms
                            ))
                            imported += 1
                    except json.JSONDecodeError:
                        continue

            conn.commit()
            if imported > 0:
                logger.info(f"Imported {imported} new prompt history entries")
        finally:
            conn.close()

    def _import_stats(self):
        """Import usage statistics from stats-cache.json."""
        stats_file = self.log_path / 'stats-cache.json'
        if not stats_file.exists():
            return

        conn = sqlite3.connect(self.db_path)
        try:
            with open(stats_file, 'r', encoding='utf-8') as f:
                stats = json.load(f)

            # Import model usage stats
            model_usage = stats.get('modelUsage', {})
            now = datetime.now().isoformat()

            for model, usage in model_usage.items():
                conn.execute('''
                    INSERT OR REPLACE INTO usage_stats
                    (stat_date, model, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    stats.get('lastComputedDate', 'unknown'),
                    model,
                    usage.get('inputTokens', 0),
                    usage.get('outputTokens', 0),
                    usage.get('cacheReadInputTokens', 0),
                    usage.get('cacheCreationInputTokens', 0),
                    now
                ))

            conn.commit()
            logger.info(f"Updated usage stats for {len(model_usage)} models")
        except Exception as e:
            logger.error(f"Error importing stats: {e}")
        finally:
            conn.close()

    def _import_plans(self):
        """Import implementation plans from plans/ directory."""
        plans_dir = self.log_path / 'plans'
        if not plans_dir.exists():
            return

        conn = sqlite3.connect(self.db_path)
        try:
            imported = 0
            for plan_file in plans_dir.glob('*.md'):
                file_hash = self._file_hash(plan_file)

                # Check if already imported with same hash
                cursor = conn.execute(
                    "SELECT 1 FROM plans WHERE name = ? AND file_hash = ?",
                    (plan_file.stem, file_hash)
                )
                if cursor.fetchone():
                    continue

                content = plan_file.read_text(encoding='utf-8')
                # Extract title from first heading
                title = plan_file.stem
                for line in content.split('\n'):
                    if line.startswith('# '):
                        title = line[2:].strip()
                        break

                mtime = datetime.fromtimestamp(plan_file.stat().st_mtime).isoformat()

                conn.execute('''
                    INSERT OR REPLACE INTO plans (name, title, content, created_at, file_hash)
                    VALUES (?, ?, ?, ?, ?)
                ''', (plan_file.stem, title, content, mtime, file_hash))
                imported += 1

            conn.commit()
            if imported > 0:
                logger.info(f"Imported {imported} plans")
        finally:
            conn.close()

    def _import_todos(self):
        """Import session todos from todos/ directory."""
        todos_dir = self.log_path / 'todos'
        if not todos_dir.exists():
            return

        conn = sqlite3.connect(self.db_path)
        try:
            imported = 0
            for todo_file in todos_dir.glob('*.json'):
                # Extract session ID from filename (format: sessionid-agent-sessionid.json)
                parts = todo_file.stem.split('-agent-')
                session_id = parts[0] if parts else todo_file.stem

                try:
                    with open(todo_file, 'r', encoding='utf-8') as f:
                        todos = json.load(f)

                    if not todos:  # Skip empty todo lists
                        continue

                    # Check if already imported
                    cursor = conn.execute(
                        "SELECT 1 FROM session_todos WHERE session_id = ?",
                        (session_id,)
                    )
                    if cursor.fetchone():
                        continue

                    for idx, todo in enumerate(todos):
                        if isinstance(todo, dict):
                            conn.execute('''
                                INSERT INTO session_todos (session_id, content, status, sequence)
                                VALUES (?, ?, ?, ?)
                            ''', (
                                session_id,
                                todo.get('content', str(todo)),
                                todo.get('status', 'unknown'),
                                idx
                            ))
                            imported += 1
                except (json.JSONDecodeError, Exception):
                    continue

            conn.commit()
            if imported > 0:
                logger.info(f"Imported {imported} todo items")
        finally:
            conn.close()

    def process_all(self):
        """Process all log files in the log directory."""
        if not self.log_path.exists():
            logger.warning(f"Log path does not exist: {self.log_path}")
            return

        # Import additional data sources
        self._import_prompt_history()
        self._import_stats()
        self._import_plans()
        self._import_todos()
        
        # Find actual session JSONL files in projects directory
        patterns = ['projects/**/*.jsonl']
        log_files = []
        for pattern in patterns:
            log_files.extend(self.log_path.glob(pattern))
        
        processed = 0
        skipped = 0
        errors = 0
        
        for filepath in log_files:
            # Skip very small files (likely not real logs)
            if filepath.stat().st_size < 50:
                continue
                
            # Skip already processed files
            if self._is_processed(filepath):
                skipped += 1
                continue
            
            parsed = self._parse_claude_code_log(filepath)
            if parsed and parsed.get('messages'):
                try:
                    self._import_session(parsed, self._file_hash(filepath))
                    processed += 1
                except Exception as e:
                    logger.error(f"Failed to import {filepath}: {e}")
                    errors += 1
            else:
                logger.debug(f"Skipped {filepath}: no valid content")
        
        logger.info(f"Processing complete: {processed} imported, {skipped} skipped, {errors} errors")


def main():
    db_path = os.environ.get('DB_PATH', '/data/sessions.db')
    log_path = os.environ.get('LOG_PATH', '/claude-logs')
    watch_interval = int(os.environ.get('WATCH_INTERVAL', 30))
    
    processor = LogProcessor(db_path, log_path)
    
    logger.info(f"Starting log processor (interval: {watch_interval}s)")
    logger.info(f"Watching: {log_path}")
    logger.info(f"Database: {db_path}")
    
    while True:
        try:
            processor.process_all()
        except Exception as e:
            logger.error(f"Processing error: {e}")
        
        time.sleep(watch_interval)


if __name__ == '__main__':
    main()
