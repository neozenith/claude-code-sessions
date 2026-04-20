"""
Database abstraction layer for Claude Code Sessions analytics.

Re-exports the Protocol and the SQLite implementation so external code
can import from ``claude_code_sessions.database`` without knowing the
internal package structure.

Usage::

    from claude_code_sessions.database import Database, SQLiteDatabase
"""

from claude_code_sessions.database.protocol import Database
from claude_code_sessions.database.sqlite import SQLiteDatabase

__all__ = ["Database", "SQLiteDatabase"]
