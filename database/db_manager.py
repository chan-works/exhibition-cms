import sqlite3
import bcrypt
import json
from pathlib import Path


class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            app_dir = Path.home() / ".exhibition_cms"
            app_dir.mkdir(exist_ok=True)
            db_path = app_dir / "exhibition_cms.db"
        self.db_path = str(db_path)
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name TEXT,
                    role TEXT NOT NULL DEFAULT 'operator',
                    is_active INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS zones (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    color TEXT DEFAULT '#2196F3',
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zone_id INTEGER,
                    name TEXT NOT NULL,
                    device_type TEXT NOT NULL,
                    config TEXT NOT NULL DEFAULT '{}',
                    is_enabled INTEGER DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zone_id INTEGER NOT NULL,
                    schedule_date TEXT NOT NULL,
                    time_on TEXT,
                    time_off TEXT,
                    is_enabled INTEGER DEFAULT 1,
                    is_holiday INTEGER DEFAULT 0,
                    holiday_name TEXT,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    updated_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE,
                    UNIQUE (zone_id, schedule_date)
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_type TEXT DEFAULT 'info',
                    title TEXT NOT NULL,
                    message TEXT,
                    is_read INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS recurring_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    zone_id INTEGER NOT NULL,
                    day_of_week INTEGER NOT NULL,
                    time_on TEXT,
                    time_off TEXT,
                    is_enabled INTEGER DEFAULT 1,
                    notes TEXT,
                    created_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (zone_id) REFERENCES zones(id) ON DELETE CASCADE,
                    UNIQUE (zone_id, day_of_week)
                );
            """)
            cursor = conn.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                pw_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
                conn.execute(
                    "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                    ("admin", pw_hash, "Administrator", "admin")
                )

    # ── Users ────────────────────────────────────────────────────────────────

    def authenticate_user(self, username, password):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND is_active = 1",
                (username,)
            ).fetchone()
            if row and bcrypt.checkpw(password.encode(), row["password_hash"].encode()):
                return dict(row)
            return None

    def get_all_users(self):
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM users ORDER BY username"
            ).fetchall()]

    def create_user(self, username, password, full_name, role):
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
                (username, pw_hash, full_name, role)
            )

    def update_user(self, user_id, full_name, role, is_active):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE users SET full_name=?, role=?, is_active=? WHERE id=?",
                (full_name, role, is_active, user_id)
            )

    def update_user_password(self, user_id, new_password):
        pw_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        with self._get_conn() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (pw_hash, user_id))

    def delete_user(self, user_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM users WHERE id=?", (user_id,))

    # ── Zones ─────────────────────────────────────────────────────────────────

    def get_all_zones(self):
        with self._get_conn() as conn:
            return [dict(r) for r in conn.execute(
                "SELECT * FROM zones ORDER BY sort_order, name"
            ).fetchall()]

    def create_zone(self, name, description="", color="#2196F3"):
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO zones (name, description, color) VALUES (?, ?, ?)",
                (name, description, color)
            )
            return cur.lastrowid

    def update_zone(self, zone_id, name, description, color):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE zones SET name=?, description=?, color=? WHERE id=?",
                (name, description, color, zone_id)
            )

    def delete_zone(self, zone_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM zones WHERE id=?", (zone_id,))

    # ── Devices ───────────────────────────────────────────────────────────────

    def get_all_devices(self):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT d.*, z.name as zone_name, z.color as zone_color
                FROM devices d
                LEFT JOIN zones z ON d.zone_id = z.id
                ORDER BY z.name, d.sort_order, d.name
            """).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["config"] = json.loads(d["config"])
                except Exception:
                    d["config"] = {}
                result.append(d)
            return result

    def get_devices_by_zone(self, zone_id):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM devices WHERE zone_id=? AND is_enabled=1 ORDER BY sort_order, name",
                (zone_id,)
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                try:
                    d["config"] = json.loads(d["config"])
                except Exception:
                    d["config"] = {}
                result.append(d)
            return result

    def create_device(self, zone_id, name, device_type, config):
        with self._get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO devices (zone_id, name, device_type, config) VALUES (?, ?, ?, ?)",
                (zone_id, name, device_type, json.dumps(config))
            )
            return cur.lastrowid

    def update_device(self, device_id, zone_id, name, device_type, config, is_enabled):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE devices SET zone_id=?, name=?, device_type=?, config=?, is_enabled=? WHERE id=?",
                (zone_id, name, device_type, json.dumps(config), is_enabled, device_id)
            )

    def delete_device(self, device_id):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM devices WHERE id=?", (device_id,))

    # ── Schedules ─────────────────────────────────────────────────────────────

    def get_schedule(self, zone_id, date_str):
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM schedules WHERE zone_id=? AND schedule_date=?",
                (zone_id, date_str)
            ).fetchone()
            return dict(row) if row else None

    def get_schedules_for_date(self, date_str):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT s.*, z.name as zone_name, z.color as zone_color
                FROM schedules s
                JOIN zones z ON s.zone_id = z.id
                WHERE s.schedule_date = ?
                ORDER BY z.name
            """, (date_str,)).fetchall()
            return [dict(r) for r in rows]

    def get_schedules_for_month(self, year, month):
        date_prefix = f"{year:04d}-{month:02d}"
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM schedules WHERE schedule_date LIKE ? ORDER BY schedule_date",
                (f"{date_prefix}%",)
            ).fetchall()
            return [dict(r) for r in rows]

    def save_schedule(self, zone_id, date_str, time_on, time_off,
                      is_enabled, is_holiday, holiday_name, notes):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO schedules
                    (zone_id, schedule_date, time_on, time_off, is_enabled, is_holiday, holiday_name, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(zone_id, schedule_date) DO UPDATE SET
                    time_on=excluded.time_on,
                    time_off=excluded.time_off,
                    is_enabled=excluded.is_enabled,
                    is_holiday=excluded.is_holiday,
                    holiday_name=excluded.holiday_name,
                    notes=excluded.notes,
                    updated_at=datetime('now')
            """, (zone_id, date_str, time_on, time_off, is_enabled, is_holiday, holiday_name, notes))

    def delete_schedule(self, zone_id, date_str):
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM schedules WHERE zone_id=? AND schedule_date=?",
                (zone_id, date_str)
            )

    def get_todays_schedules(self):
        from datetime import date
        return self.get_schedules_for_date(date.today().isoformat())

    # ── Notifications ─────────────────────────────────────────────────────────

    def add_notification(self, ntype, title, message=""):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO notifications (notification_type, title, message) VALUES (?, ?, ?)",
                (ntype, title, message)
            )

    def get_notifications(self, limit=100):
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM notifications ORDER BY created_at DESC LIMIT ?",
                (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_unread_count(self):
        with self._get_conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE is_read=0"
            ).fetchone()[0]

    def mark_notification_read(self, notification_id):
        with self._get_conn() as conn:
            conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))

    def mark_all_notifications_read(self):
        with self._get_conn() as conn:
            conn.execute("UPDATE notifications SET is_read=1")

    def clear_old_notifications(self, days=30):
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM notifications WHERE created_at < datetime('now', ?)",
                (f"-{days} days",)
            )

    # ── Settings ──────────────────────────────────────────────────────────────

    # ── Recurring Schedules ───────────────────────────────────────────────────

    def get_recurring_schedules(self, zone_id):
        """Returns list of 7 entries (0=Mon … 6=Sun), None if not set."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM recurring_schedules WHERE zone_id=? ORDER BY day_of_week",
                (zone_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_recurring_schedules(self):
        with self._get_conn() as conn:
            rows = conn.execute("""
                SELECT r.*, z.name as zone_name, z.color as zone_color
                FROM recurring_schedules r
                JOIN zones z ON r.zone_id = z.id
                ORDER BY z.name, r.day_of_week
            """).fetchall()
            return [dict(r) for r in rows]

    def save_recurring_schedule(self, zone_id, day_of_week, time_on, time_off, is_enabled, notes=""):
        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO recurring_schedules
                    (zone_id, day_of_week, time_on, time_off, is_enabled, notes)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(zone_id, day_of_week) DO UPDATE SET
                    time_on=excluded.time_on,
                    time_off=excluded.time_off,
                    is_enabled=excluded.is_enabled,
                    notes=excluded.notes
            """, (zone_id, day_of_week, time_on, time_off, is_enabled, notes))

    def delete_recurring_schedule(self, zone_id, day_of_week):
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM recurring_schedules WHERE zone_id=? AND day_of_week=?",
                (zone_id, day_of_week)
            )

    def get_effective_schedule_for_today(self, zone_id):
        """Returns today's specific schedule if exists, else recurring schedule."""
        from datetime import date
        today = date.today()
        date_str = today.isoformat()
        day_of_week = today.weekday()  # 0=Mon, 6=Sun

        specific = self.get_schedule(zone_id, date_str)
        if specific:
            return specific, "specific"

        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM recurring_schedules WHERE zone_id=? AND day_of_week=? AND is_enabled=1",
                (zone_id, day_of_week)
            ).fetchone()
            if row:
                return dict(row), "recurring"
        return None, None

    def get_setting(self, key, default=None):
        with self._get_conn() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key, value):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value))
            )
