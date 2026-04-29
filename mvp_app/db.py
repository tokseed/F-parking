from __future__ import annotations

import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "parking_mvp.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id TEXT UNIQUE,
            name TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            home_area TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS parking_spots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            area TEXT NOT NULL,
            address TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'free',
            confidence INTEGER NOT NULL DEFAULT 50,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            starts_at TEXT NOT NULL,
            ends_at TEXT NOT NULL,
            amount_rub INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spot_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(spot_id) REFERENCES parking_spots(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )

    conn.commit()
    conn.close()


def seed_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    user_count = cur.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if user_count:
        conn.close()
        return

    cur.execute(
        """
        INSERT INTO users (telegram_id, name, role, home_area)
        VALUES
        ('10001', 'Анна', 'user', 'Александровка'),
        ('10002', 'Илья', 'moderator', 'Александровка'),
        ('10003', 'Мария', 'user', 'Александровка')
        """
    )

    cur.execute(
        """
        INSERT INTO parking_spots (
            user_id, area, address, latitude, longitude, status, confidence, expires_at
        )
        VALUES
        (1, 'Александровка', 'ул. 40-летия Победы, 63', 47.2369, 39.8121, 'free', 82, datetime('now', '+12 minutes')),
        (3, 'Александровка', 'пр. 40-летия Победы, 85/4', 47.2357, 39.8184, 'free', 67, datetime('now', '+8 minutes'))
        """
    )

    cur.execute(
        """
        INSERT INTO subscriptions (user_id, plan, status, starts_at, ends_at, amount_rub)
        VALUES
        (1, 'day', 'active', datetime('now'), datetime('now', '+1 day'), 300),
        (3, '3days', 'active', datetime('now'), datetime('now', '+3 days'), 750)
        """
    )

    conn.commit()
    conn.close()
