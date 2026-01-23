#!/usr/bin/env python3
"""CLI tool for managing users and API keys."""
import argparse
import hashlib
import secrets
import sys
import psycopg2
from psycopg2.extras import RealDictCursor


def generate_api_key() -> str:
    """Generate a new API key."""
    return f"dkd_sk_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    """Hash API key with SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def create_user(conn, username: str, email: str = None, share_level: str = "metadata", is_admin: bool = False):
    """Create a new user and return their API key."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO users (username, api_key_hash, email, share_level, is_admin)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        """, (username, key_hash, email, share_level, is_admin))
        user_id = cur.fetchone()["id"]
        conn.commit()

    print(f"Created user: {username} (ID: {user_id}){' [ADMIN]' if is_admin else ''}")
    print(f"API Key: {api_key}")
    print("\nSave this API key - it cannot be retrieved later!")
    return api_key


def list_users(conn):
    """List all users."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                u.id, u.username, u.email, u.share_level,
                u.created_at, u.last_seen_at,
                COUNT(s.id) as sessions
            FROM users u
            LEFT JOIN sessions s ON s.user_id = u.id
            GROUP BY u.id
            ORDER BY u.username
        """)
        users = cur.fetchall()

    print(f"{'ID':<5} {'Username':<20} {'Email':<30} {'Level':<10} {'Sessions':<10} {'Last Seen':<20}")
    print("-" * 95)
    for u in users:
        last_seen = u["last_seen_at"].strftime("%Y-%m-%d %H:%M") if u["last_seen_at"] else "never"
        print(f"{u['id']:<5} {u['username']:<20} {u['email'] or '-':<30} {u['share_level']:<10} {u['sessions']:<10} {last_seen:<20}")


def rotate_key(conn, username: str):
    """Generate a new API key for a user."""
    api_key = generate_api_key()
    key_hash = hash_api_key(api_key)

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE users SET api_key_hash = %s WHERE username = %s RETURNING id
        """, (key_hash, username))
        result = cur.fetchone()
        if not result:
            print(f"Error: User '{username}' not found")
            sys.exit(1)
        conn.commit()

    print(f"New API Key for {username}: {api_key}")
    print("\nSave this API key - it cannot be retrieved later!")


def delete_user(conn, username: str):
    """Delete a user and their data."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        if not user:
            print(f"Error: User '{username}' not found")
            sys.exit(1)

        # Delete sessions (cascades to messages, tool_usage, tags)
        cur.execute("DELETE FROM sessions WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM daily_stats WHERE user_id = %s", (user["id"],))
        cur.execute("DELETE FROM users WHERE id = %s", (user["id"],))
        conn.commit()

    print(f"Deleted user: {username}")


def main():
    import os
    db_url = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")
    # Strip async driver prefix for psycopg2
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    parser = argparse.ArgumentParser(description="Claude Insights User Management")
    parser.add_argument("--db", default=db_url)

    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-user
    create_parser = subparsers.add_parser("create-user", help="Create a new user")
    create_parser.add_argument("username")
    create_parser.add_argument("--email", "-e")
    create_parser.add_argument("--share-level", "-s", default="metadata", choices=["none", "metadata", "full"])
    create_parser.add_argument("--admin", "-a", action="store_true", help="Grant admin privileges")

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    # rotate-key
    rotate_parser = subparsers.add_parser("rotate-key", help="Generate new API key for user")
    rotate_parser.add_argument("username")

    # delete-user
    delete_parser = subparsers.add_parser("delete-user", help="Delete a user")
    delete_parser.add_argument("username")

    args = parser.parse_args()

    conn = psycopg2.connect(args.db, cursor_factory=RealDictCursor)

    try:
        if args.command == "create-user":
            create_user(conn, args.username, args.email, args.share_level, args.admin)
        elif args.command == "list-users":
            list_users(conn)
        elif args.command == "rotate-key":
            rotate_key(conn, args.username)
        elif args.command == "delete-user":
            delete_user(conn, args.username)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
