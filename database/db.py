"""SQLite connections, schema initialization, and demo data for Spendly."""

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from werkzeug.security import generate_password_hash


DB_PATH = Path(__file__).resolve().parent.parent / "expense_tracker.db"


class DuplicateEmailError(Exception):
    """An account already uses the submitted email address."""


def create_user(name, email, password):
    """Save validated, normalized registration data and return the user ID.

    The caller supplies a trimmed name and a trimmed, lowercase email.
    Duplicate emails raise DuplicateEmailError; other errors propagate.
    """
    password_hash = generate_password_hash(password)
    with closing(get_db()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            # Match Python's email normalization, including non-ASCII letters.
            # Hold the write lock across both the duplicate check and insert.
            existing_emails = connection.execute("SELECT email FROM users")
            if any(row["email"].lower() == email for row in existing_emails):
                raise DuplicateEmailError()

            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) "
                "VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            user_id = cursor.lastrowid
    return user_id


def get_db():
    """Return a configured connection; the caller is responsible for closing it."""
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
    except sqlite3.Error:
        connection.close()
        raise
    return connection


def init_db():
    """Create the schema without changing existing tables or data."""
    with closing(get_db()) as connection:
        with connection:
            connection.execute("BEGIN")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL REFERENCES users(id),
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    date TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT DEFAULT (datetime('now'))
                )
                """
            )


def seed_db():
    """Atomically add demo data only when the initialized database has no users."""
    with closing(get_db()) as connection:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                return

            cursor = connection.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (
                    "Demo User",
                    "demo@spendly.com",
                    generate_password_hash("demo123"),
                ),
            )
            user_id = cursor.lastrowid
            current_date = date.today()
            samples = (
                (1, "Food", 12.50),
                (4, "Transport", 20.00),
                (8, "Bills", 75.00),
                (12, "Health", 30.00),
                (16, "Entertainment", 18.00),
                (20, "Shopping", 45.00),
                (24, "Other", 10.00),
                (28, "Food", 25.00),
            )
            connection.executemany(
                """
                INSERT INTO expenses (user_id, amount, category, date, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        amount,
                        category,
                        current_date.replace(day=day).isoformat(),
                        None,
                    )
                    for day, category, amount in samples
                ],
            )
