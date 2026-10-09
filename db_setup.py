"""
db_setup.py
-----------
Creates the SQLite database (hospital.db) and seeds it with
realistic initial data for all branches and departments.

Run once:
    python db_setup.py
"""

import sqlite3
import random
import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

_IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    """Return current datetime in Asia/Kolkata timezone."""
    return datetime.now(_IST)

DB_PATH = "hospital.db"

BRANCHES = ["Main Campus", "North Wing", "South Wing", "East Campus", "Pediatrics"]

DEPARTMENTS = {
    "Main Campus":  ["Emergency", "Cardiology", "Neurology", "Orthopedics", "General"],
    "North Wing":   ["ICU", "Oncology", "Pulmonology", "General"],
    "South Wing":   ["Maternity", "Neonatal", "Surgery", "General"],
    "East Campus":  ["Psychiatry", "Rehabilitation", "General"],
    "Pediatrics":   ["PICU", "Pediatric Surgery", "Pediatric General"],
}

EQUIPMENT_TYPES = [
    "Ventilators", "MRI Machines", "CT Scanners", "ECG Monitors",
    "Defibrillators", "Infusion Pumps", "Dialysis Machines", "X-Ray Units",
    "Anesthesia Machines", "Patient Monitors",
]

EQUIPMENT_STATUS = ["operational", "maintenance", "out_of_service"]


# ── Schema ─────────────────────────────────────────────────────────────────────

CREATE_BRANCHES = """
CREATE TABLE IF NOT EXISTS branches (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE
);
"""

CREATE_DEPARTMENTS = """
CREATE TABLE IF NOT EXISTS departments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id   INTEGER NOT NULL REFERENCES branches(id),
    name        TEXT NOT NULL,
    total_beds  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(branch_id, name)
);
"""

CREATE_BED_OCCUPANCY = """
CREATE TABLE IF NOT EXISTS bed_occupancy (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    department_id   INTEGER NOT NULL REFERENCES departments(id),
    occupied_beds   INTEGER NOT NULL DEFAULT 0,
    icu_total       INTEGER NOT NULL DEFAULT 0,
    icu_occupied    INTEGER NOT NULL DEFAULT 0,
    recorded_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

CREATE_EQUIPMENT = """
CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id   INTEGER NOT NULL REFERENCES branches(id),
    name        TEXT NOT NULL,
    status      TEXT NOT NULL CHECK(status IN ('operational','maintenance','out_of_service')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(branch_id, name, status)
);
"""

CREATE_OCCUPANCY_TREND = """
CREATE TABLE IF NOT EXISTS occupancy_trend (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    branch_id   INTEGER NOT NULL REFERENCES branches(id),
    recorded_at TEXT NOT NULL,
    occupancy_pct REAL NOT NULL
);
"""

CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    level       TEXT NOT NULL CHECK(level IN ('critical','warning','info')),
    message     TEXT NOT NULL,
    branch      TEXT,
    department  TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    resolved    INTEGER NOT NULL DEFAULT 0
);
"""


def seed(conn: sqlite3.Connection):
    rng = random.Random(42)
    cur = conn.cursor()

    # ── Branches ──────────────────────────────────────────────────────────────
    for b in BRANCHES:
        cur.execute("INSERT OR IGNORE INTO branches(name) VALUES(?)", (b,))

    branch_ids = {row[1]: row[0] for row in cur.execute("SELECT id, name FROM branches")}

    # ── Departments + current occupancy ───────────────────────────────────────
    now_str = _now_ist().strftime("%Y-%m-%d %H:%M:%S")
    for branch, depts in DEPARTMENTS.items():
        bid = branch_ids[branch]
        for dept in depts:
            total = rng.randint(20, 80)
            occupied = rng.randint(int(total * 0.4), total)
            icu_total = (rng.randint(4, 20)
                         if any(k in dept for k in ("ICU", "Emergency", "PICU"))
                         else rng.randint(2, 10))
            icu_occupied = rng.randint(int(icu_total * 0.3), icu_total)

            cur.execute(
                "INSERT OR IGNORE INTO departments(branch_id, name, total_beds) VALUES(?,?,?)",
                (bid, dept, total),
            )
            dept_id = cur.execute(
                "SELECT id FROM departments WHERE branch_id=? AND name=?", (bid, dept)
            ).fetchone()[0]

            cur.execute(
                "INSERT INTO bed_occupancy(department_id, occupied_beds, icu_total, icu_occupied, recorded_at)"
                " VALUES(?,?,?,?,?)",
                (dept_id, occupied, icu_total, icu_occupied, now_str),
            )

    # ── Equipment ─────────────────────────────────────────────────────────────
    for branch in BRANCHES:
        bid = branch_ids[branch]
        for eq in EQUIPMENT_TYPES:
            total = rng.randint(3, 15)
            operational  = rng.randint(int(total * 0.5), total)
            maintenance  = rng.randint(0, total - operational)
            oos          = total - operational - maintenance

            for status, count in [
                ("operational",   operational),
                ("maintenance",   maintenance),
                ("out_of_service", oos),
            ]:
                if count > 0:
                    cur.execute(
                        "INSERT OR REPLACE INTO equipment(branch_id, name, status, updated_at)"
                        " VALUES(?,?,?,?)",
                        (bid, eq, status, now_str),
                    )
                    # store count in a separate column — extend schema slightly
                    cur.execute(
                        "UPDATE equipment SET updated_at=? WHERE branch_id=? AND name=? AND status=?",
                        (now_str, bid, eq, status),
                    )

    # ── 24-hour occupancy trend ────────────────────────────────────────────────
    now = _now_ist().replace(minute=0, second=0, microsecond=0)
    for branch in BRANCHES:
        bid = branch_ids[branch]
        base = rng.uniform(55, 85)
        for h in range(24):
            ts = now - timedelta(hours=24 - h)
            noise = rng.gauss(0, 3)
            wave  = 8 * math.sin(math.pi * (ts.hour - 7) / 12)
            occ   = round(min(99, max(30, base + wave + noise)), 1)
            cur.execute(
                "INSERT INTO occupancy_trend(branch_id, recorded_at, occupancy_pct) VALUES(?,?,?)",
                (bid, ts.strftime("%Y-%m-%d %H:%M:%S"), occ),
            )

    conn.commit()
    print(f"Database seeded -> {DB_PATH}")


def create_schema(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.executescript(
        CREATE_BRANCHES
        + CREATE_DEPARTMENTS
        + CREATE_BED_OCCUPANCY
        + CREATE_EQUIPMENT
        + CREATE_OCCUPANCY_TREND
        + CREATE_ALERTS
    )

    # Add count column to equipment if missing (safe migration)
    cols = [r[1] for r in cur.execute("PRAGMA table_info(equipment)")]
    if "count" not in cols:
        cur.execute("ALTER TABLE equipment ADD COLUMN count INTEGER NOT NULL DEFAULT 1")

    conn.commit()
    print("Schema created OK")


if __name__ == "__main__":
    import os
    if os.path.exists(DB_PATH):
        ans = input(f"'{DB_PATH}' already exists. Re-seed? [y/N]: ").strip().lower()
        if ans != "y":
            print("Aborted.")
            exit(0)
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    create_schema(conn)
    seed(conn)
    conn.close()
    print(f"\nDone! Run the dashboard with:\n  python -m streamlit run app.py")
