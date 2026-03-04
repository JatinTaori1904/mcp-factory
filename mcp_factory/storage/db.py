"""MCP Factory — Local SQLite storage for tracking generated servers."""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Optional


DB_PATH = Path.home() / ".mcpfactory" / "servers.db"


class MCPDatabase:
    """Local SQLite database for tracking MCP servers created by the user."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    template TEXT NOT NULL,
                    language TEXT NOT NULL,
                    output_path TEXT NOT NULL,
                    tools TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_server(
        self,
        name: str,
        prompt: str,
        template: str,
        language: str,
        output_path: str,
        tools: list[str],
    ):
        """Save a newly created MCP server to the database."""
        now = datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO servers (name, prompt, template, language, output_path, tools, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (name, prompt, template, language, output_path, json.dumps(tools), now, now),
            )
            conn.commit()

    def list_servers(self) -> list[dict]:
        """List all saved MCP servers."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT name, template, language, tools, created_at FROM servers ORDER BY created_at DESC"
            )
            rows = cursor.fetchall()

        return [
            {
                "name": row["name"],
                "template": row["template"],
                "language": row["language"],
                "tool_count": len(json.loads(row["tools"])),
                "created_at": row["created_at"][:10],
            }
            for row in rows
        ]

    def get_server(self, name: str) -> Optional[dict]:
        """Get details of a specific MCP server."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM servers WHERE name = ?", (name,))
            row = cursor.fetchone()

        if not row:
            return None

        return {
            "name": row["name"],
            "prompt": row["prompt"],
            "template": row["template"],
            "language": row["language"],
            "output_path": row["output_path"],
            "tools": json.loads(row["tools"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def delete_server(self, name: str):
        """Delete a server from the database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM servers WHERE name = ?", (name,))
            conn.commit()

    def server_exists(self, name: str) -> bool:
        """Check if a server with the given name exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT 1 FROM servers WHERE name = ?", (name,))
            return cursor.fetchone() is not None
