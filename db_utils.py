"""
db_utils.py
-----------
All SQLite query helpers used by app.py.
Every function returns a pandas DataFrame or a plain Python value.
"""

import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "hospital.db"


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ── Bed occupancy ──────────────────────────────────────────────────────────────

def get_bed_occupancy() -> pd.DataFrame:
    """
    Returns the latest bed occupancy snapshot per department.
    Columns: branch, department, total_beds, occupied_beds, available_beds,
             occupancy_pct, icu_total, icu_occupied, icu_available, icu_occupancy_pct
    """
    sql = """
        SELECT
            b.name                                          AS branch,
            d.name                                          AS department,
            d.total_beds,
            bo.occupied_beds,
            d.total_beds - bo.occupied_beds                 AS available_beds,
            ROUND(bo.occupied_beds * 100.0 / d.total_beds, 1) AS occupancy_pct,
            bo.icu_total,
            bo.icu_occupied,
            bo.icu_total - bo.icu_occupied                  AS icu_available,
            ROUND(bo.icu_occupied * 100.0 / bo.icu_total, 1) AS icu_occupancy_pct
        FROM bed_occupancy bo
        JOIN departments d ON d.id = bo.department_id
        JOIN branches    b ON b.id = d.branch_id
        WHERE bo.id IN (
            -- latest record per department
            SELECT MAX(id) FROM bed_occupancy GROUP BY department_id
        )
        ORDER BY b.name, d.name
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


def update_bed_occupancy(branch: str, department: str,
                          occupied: int, icu_occupied: int) -> None:
    """Insert a new occupancy snapshot for the given department."""
    sql_dept = """
        SELECT d.id, d.total_beds, bo.icu_total
        FROM departments d
        JOIN branches b ON b.id = d.branch_id
        LEFT JOIN bed_occupancy bo ON bo.department_id = d.id
        WHERE b.name = ? AND d.name = ?
        ORDER BY bo.id DESC LIMIT 1
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        row = conn.execute(sql_dept, (branch, department)).fetchone()
        if row is None:
            raise ValueError(f"Department '{department}' in '{branch}' not found.")
        dept_id, total_beds, icu_total = row
        occupied  = max(0, min(occupied,  total_beds))
        icu_occupied = max(0, min(icu_occupied, icu_total or 0))
        conn.execute(
            "INSERT INTO bed_occupancy(department_id, occupied_beds, icu_total, icu_occupied, recorded_at)"
            " VALUES(?,?,?,?,?)",
            (dept_id, occupied, icu_total or 0, icu_occupied, now_str),
        )
        conn.commit()


# ── Equipment ──────────────────────────────────────────────────────────────────

def get_equipment_status() -> pd.DataFrame:
    """
    Returns equipment counts per branch × equipment type × status.
    Columns: branch, equipment, total, operational, maintenance, out_of_service, operational_pct
    """
    sql = """
        SELECT
            b.name      AS branch,
            e.name      AS equipment,
            SUM(e.count)                                        AS total,
            SUM(CASE WHEN e.status='operational'   THEN e.count ELSE 0 END) AS operational,
            SUM(CASE WHEN e.status='maintenance'   THEN e.count ELSE 0 END) AS maintenance,
            SUM(CASE WHEN e.status='out_of_service'THEN e.count ELSE 0 END) AS out_of_service,
            ROUND(
                SUM(CASE WHEN e.status='operational' THEN e.count ELSE 0 END)
                * 100.0 / SUM(e.count), 1
            ) AS operational_pct
        FROM equipment e
        JOIN branches b ON b.id = e.branch_id
        GROUP BY b.name, e.name
        ORDER BY b.name, e.name
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


def update_equipment(branch: str, equipment: str,
                     operational: int, maintenance: int, out_of_service: int) -> None:
    """Overwrite equipment counts for a given branch + equipment type."""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        bid = conn.execute("SELECT id FROM branches WHERE name=?", (branch,)).fetchone()
        if bid is None:
            raise ValueError(f"Branch '{branch}' not found.")
        bid = bid[0]
        for status, count in [
            ("operational", operational),
            ("maintenance", maintenance),
            ("out_of_service", out_of_service),
        ]:
            conn.execute(
                """INSERT INTO equipment(branch_id, name, status, count, updated_at)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(branch_id, name, status)
                   DO UPDATE SET count=excluded.count, updated_at=excluded.updated_at""",
                (bid, equipment, status, count, now_str),
            )
        conn.commit()


# ── Trend ──────────────────────────────────────────────────────────────────────

def get_occupancy_trend(hours: int = 24) -> pd.DataFrame:
    """
    Returns hourly occupancy trend for all branches over the last `hours` hours.
    Columns: timestamp, branch, occupancy_pct
    """
    sql = """
        SELECT
            ot.recorded_at  AS timestamp,
            b.name          AS branch,
            ot.occupancy_pct
        FROM occupancy_trend ot
        JOIN branches b ON b.id = ot.branch_id
        WHERE ot.recorded_at >= datetime('now', ? || ' hours')
        ORDER BY ot.recorded_at, b.name
    """
    with _conn() as conn:
        df = pd.read_sql_query(sql, conn, params=(f"-{hours}",))
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def append_trend_snapshot(occupancy_by_branch: dict) -> None:
    """
    Insert a new trend row for each branch.
    occupancy_by_branch = {"Main Campus": 78.5, "North Wing": 82.1, ...}
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        for branch, pct in occupancy_by_branch.items():
            bid = conn.execute("SELECT id FROM branches WHERE name=?", (branch,)).fetchone()
            if bid:
                conn.execute(
                    "INSERT INTO occupancy_trend(branch_id, recorded_at, occupancy_pct) VALUES(?,?,?)",
                    (bid[0], now_str, round(pct, 1)),
                )
        conn.commit()


# ── Alerts ─────────────────────────────────────────────────────────────────────

def get_active_alerts() -> pd.DataFrame:
    """Returns all unresolved alerts, newest first."""
    sql = """
        SELECT id, level, message, branch, department, created_at
        FROM alerts
        WHERE resolved = 0
        ORDER BY created_at DESC
        LIMIT 50
    """
    with _conn() as conn:
        return pd.read_sql_query(sql, conn)


def insert_alert(level: str, message: str,
                 branch: str = None, department: str = None) -> None:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _conn() as conn:
        conn.execute(
            "INSERT INTO alerts(level, message, branch, department, created_at) VALUES(?,?,?,?,?)",
            (level, message, branch, department, now_str),
        )
        conn.commit()


def resolve_alert(alert_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE alerts SET resolved=1 WHERE id=?", (alert_id,))
        conn.commit()


def resolve_all_alerts() -> None:
    with _conn() as conn:
        conn.execute("UPDATE alerts SET resolved=1")
        conn.commit()


# ── Summary stats (used by KPI row) ───────────────────────────────────────────

def get_branch_list() -> list[str]:
    with _conn() as conn:
        rows = conn.execute("SELECT name FROM branches ORDER BY name").fetchall()
    return [r[0] for r in rows]


def db_exists() -> bool:
    import os
    return os.path.exists(DB_PATH)
