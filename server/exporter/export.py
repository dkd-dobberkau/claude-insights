"""Parquet exporter for daily session snapshots and cleanup."""

import os
import logging
import schedule
import time
from datetime import date, timedelta
from pathlib import Path
import psycopg2
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://insights:password@localhost/claude_insights")
BACKUP_DIR = Path(os.environ.get("BACKUP_DIR", "/backup/parquet"))
EXPORT_SCHEDULE = os.environ.get("EXPORT_SCHEDULE", "02:00")


def get_db():
    """Get database connection."""
    return psycopg2.connect(DATABASE_URL)


def export_daily_snapshot():
    """Export yesterday's data to Parquet files."""
    yesterday = date.today() - timedelta(days=1)
    output_dir = BACKUP_DIR / f"year={yesterday.year}" / f"month={yesterday.month:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Exporting data for {yesterday}")

    try:
        with get_db() as conn:
            # Export sessions
            sessions_df = pd.read_sql("""
                SELECT
                    s.id as session_id,
                    u.username,
                    s.project_name,
                    s.started_at,
                    s.ended_at,
                    s.duration_seconds,
                    s.total_messages,
                    s.total_tokens_in,
                    s.total_tokens_out,
                    s.model
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE DATE(s.started_at) = %s
            """, conn, params=[yesterday])

            if not sessions_df.empty:
                sessions_path = output_dir / f"sessions_{yesterday.isoformat()}.parquet"
                pq.write_table(
                    pa.Table.from_pandas(sessions_df),
                    sessions_path,
                    compression="snappy"
                )
                logger.info(f"Exported {len(sessions_df)} sessions to {sessions_path}")

            # Export tool usage
            tools_df = pd.read_sql("""
                SELECT
                    t.session_id,
                    t.tool_name,
                    t.call_count,
                    t.success_count,
                    t.error_count
                FROM tool_usage t
                JOIN sessions s ON t.session_id = s.id
                WHERE DATE(s.started_at) = %s
            """, conn, params=[yesterday])

            if not tools_df.empty:
                tools_path = output_dir / f"tools_{yesterday.isoformat()}.parquet"
                pq.write_table(
                    pa.Table.from_pandas(tools_df),
                    tools_path,
                    compression="snappy"
                )
                logger.info(f"Exported {len(tools_df)} tool records to {tools_path}")

            # Update daily_stats aggregation
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO daily_stats (user_id, stat_date, session_count, total_tokens_in, total_tokens_out, total_duration_seconds, top_tools)
                    SELECT
                        s.user_id,
                        DATE(s.started_at),
                        COUNT(*),
                        SUM(s.total_tokens_in),
                        SUM(s.total_tokens_out),
                        SUM(s.duration_seconds),
                        (
                            SELECT jsonb_object_agg(tool_name, call_count)
                            FROM (
                                SELECT t.tool_name, SUM(t.call_count) as call_count
                                FROM tool_usage t
                                WHERE t.session_id IN (SELECT id FROM sessions WHERE user_id = s.user_id AND DATE(started_at) = DATE(s.started_at))
                                GROUP BY t.tool_name
                                ORDER BY call_count DESC
                                LIMIT 5
                            ) top
                        )
                    FROM sessions s
                    WHERE DATE(s.started_at) = %s
                    GROUP BY s.user_id, DATE(s.started_at)
                    ON CONFLICT (user_id, stat_date) DO UPDATE SET
                        session_count = EXCLUDED.session_count,
                        total_tokens_in = EXCLUDED.total_tokens_in,
                        total_tokens_out = EXCLUDED.total_tokens_out,
                        total_duration_seconds = EXCLUDED.total_duration_seconds,
                        top_tools = EXCLUDED.top_tools
                """, [yesterday])
                conn.commit()
                logger.info("Updated daily_stats aggregation")

    except Exception as e:
        logger.error(f"Export failed: {e}")
        raise


def cleanup_old_files():
    """Remove Parquet files older than 30 days."""
    cutoff = date.today() - timedelta(days=30)
    for parquet_file in BACKUP_DIR.glob("**/*.parquet"):
        # Extract date from filename
        try:
            file_date = date.fromisoformat(parquet_file.stem.split("_")[-1])
            if file_date < cutoff:
                parquet_file.unlink()
                logger.info(f"Deleted old file: {parquet_file}")
        except (ValueError, IndexError):
            continue


def main():
    """Main entry point with scheduling."""
    logger.info(f"Parquet exporter started, schedule: {EXPORT_SCHEDULE}")

    # Run export on startup if data exists
    export_daily_snapshot()

    # Schedule daily export
    schedule.every().day.at(EXPORT_SCHEDULE).do(export_daily_snapshot)
    schedule.every().day.at("03:00").do(cleanup_old_files)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
