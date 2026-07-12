"""
TEXNOMIX bot uchun SQLite ma'lumotlar bazasi qatlami.
Barcha yozuvlar user_id (Telegram chat_id) bo'yicha ajratiladi.
"""
import sqlite3
import uuid
import datetime
from contextlib import contextmanager

DB_PATH = "texnomix.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS processes (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    counterparty TEXT,
    stage TEXT NOT NULL,
    due_date TEXT,
    notes TEXT,
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS process_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    process_id TEXT NOT NULL,
    stage TEXT NOT NULL,
    note TEXT,
    at TEXT NOT NULL,
    FOREIGN KEY (process_id) REFERENCES processes(id)
);

CREATE TABLE IF NOT EXISTS debts (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    party TEXT NOT NULL,
    direction TEXT NOT NULL,     -- 'owed_to_me' | 'i_owe'
    amount REAL NOT NULL,
    currency TEXT NOT NULL,      -- 'UZS' | 'USD' | 'CNY'
    due_date TEXT,
    note TEXT,
    paid INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipes (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    category TEXT,
    base_batch REAL NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id TEXT NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def now_iso():
    return datetime.datetime.utcnow().isoformat()


def new_id():
    return uuid.uuid4().hex[:12]


# ---------------- Processes ----------------

def add_process(user_id, type_, title, counterparty, stage, due_date, notes):
    pid = new_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO processes (id, user_id, type, title, counterparty, stage, due_date, notes, completed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (pid, user_id, type_, title, counterparty, stage, due_date, notes, ts),
        )
        conn.execute(
            "INSERT INTO process_history (process_id, stage, note, at) VALUES (?, ?, ?, ?)",
            (pid, stage, notes or "", ts),
        )
    return pid


def list_processes(user_id, status="active"):
    with get_conn() as conn:
        if status == "active":
            rows = conn.execute(
                "SELECT * FROM processes WHERE user_id=? AND completed=0 ORDER BY due_date IS NULL, due_date ASC",
                (user_id,),
            ).fetchall()
        elif status == "completed":
            rows = conn.execute(
                "SELECT * FROM processes WHERE user_id=? AND completed=1 ORDER BY created_at DESC", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM processes WHERE user_id=? ORDER BY completed ASC, due_date IS NULL, due_date ASC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_process(pid):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM processes WHERE id=?", (pid,)).fetchone()
        return dict(row) if row else None


def update_process_stage(pid, new_stage, note, new_due_date=None):
    ts = now_iso()
    with get_conn() as conn:
        if new_due_date is not None:
            conn.execute(
                "UPDATE processes SET stage=?, due_date=? WHERE id=?", (new_stage, new_due_date, pid)
            )
        else:
            conn.execute("UPDATE processes SET stage=? WHERE id=?", (new_stage, pid))
        conn.execute(
            "INSERT INTO process_history (process_id, stage, note, at) VALUES (?, ?, ?, ?)",
            (pid, new_stage, note or "", ts),
        )


def toggle_process_complete(pid):
    with get_conn() as conn:
        row = conn.execute("SELECT completed FROM processes WHERE id=?", (pid,)).fetchone()
        if not row:
            return
        new_val = 0 if row["completed"] else 1
        conn.execute("UPDATE processes SET completed=? WHERE id=?", (new_val, pid))


def delete_process(pid):
    with get_conn() as conn:
        conn.execute("DELETE FROM process_history WHERE process_id=?", (pid,))
        conn.execute("DELETE FROM processes WHERE id=?", (pid,))


def get_process_history(pid, limit=5):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM process_history WHERE process_id=? ORDER BY at DESC LIMIT ?", (pid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def overdue_and_today_processes(user_id):
    today = datetime.date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM processes WHERE user_id=? AND completed=0 AND due_date IS NOT NULL AND due_date<=? ORDER BY due_date ASC",
            (user_id, today),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------- Debts ----------------

def add_debt(user_id, party, direction, amount, currency, due_date, note):
    did = new_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO debts (id, user_id, party, direction, amount, currency, due_date, note, paid, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (did, user_id, party, direction, amount, currency, due_date, note, ts),
        )
    return did


def list_debts(user_id, status="unpaid"):
    with get_conn() as conn:
        if status == "unpaid":
            rows = conn.execute(
                "SELECT * FROM debts WHERE user_id=? AND paid=0 ORDER BY due_date IS NULL, due_date ASC", (user_id,)
            ).fetchall()
        elif status == "paid":
            rows = conn.execute(
                "SELECT * FROM debts WHERE user_id=? AND paid=1 ORDER BY created_at DESC", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM debts WHERE user_id=? ORDER BY paid ASC, due_date IS NULL, due_date ASC", (user_id,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_debt(did):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM debts WHERE id=?", (did,)).fetchone()
        return dict(row) if row else None


def toggle_debt_paid(did):
    with get_conn() as conn:
        row = conn.execute("SELECT paid FROM debts WHERE id=?", (did,)).fetchone()
        if not row:
            return
        new_val = 0 if row["paid"] else 1
        conn.execute("UPDATE debts SET paid=? WHERE id=?", (new_val, did))


def delete_debt(did):
    with get_conn() as conn:
        conn.execute("DELETE FROM debts WHERE id=?", (did,))


def debt_totals(user_id):
    totals = {"owed_to_me": {}, "i_owe": {}}
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT direction, currency, SUM(amount) as total FROM debts WHERE user_id=? AND paid=0 GROUP BY direction, currency",
            (user_id,),
        ).fetchall()
        for r in rows:
            totals[r["direction"]][r["currency"]] = r["total"]
    return totals


def overdue_and_today_debts(user_id):
    today = datetime.date.today().isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM debts WHERE user_id=? AND paid=0 AND due_date IS NOT NULL AND due_date<=? ORDER BY due_date ASC",
            (user_id, today),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------- Recipes ----------------

def add_recipe(user_id, name, category, base_batch, ingredients, notes):
    rid = new_id()
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO recipes (id, user_id, name, category, base_batch, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (rid, user_id, name, category, base_batch, notes, ts),
        )
        for ing in ingredients:
            conn.execute(
                "INSERT INTO recipe_ingredients (recipe_id, name, amount, price) VALUES (?, ?, ?, ?)",
                (rid, ing["name"], ing["amount"], ing.get("price", 0)),
            )
    return rid


def list_recipes(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recipes WHERE user_id=? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_recipe(rid):
    with get_conn() as conn:
        recipe = conn.execute("SELECT * FROM recipes WHERE id=?", (rid,)).fetchone()
        if not recipe:
            return None
        ingredients = conn.execute(
            "SELECT * FROM recipe_ingredients WHERE recipe_id=? ORDER BY id ASC", (rid,)
        ).fetchall()
        result = dict(recipe)
        result["ingredients"] = [dict(i) for i in ingredients]
        return result


def delete_recipe(rid):
    with get_conn() as conn:
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id=?", (rid,))
        conn.execute("DELETE FROM recipes WHERE id=?", (rid,))


def recipe_cost(recipe):
    total_weight = sum(i["amount"] for i in recipe["ingredients"])
    total_cost = sum(i["amount"] * i["price"] for i in recipe["ingredients"])
    per_kg = total_cost / total_weight if total_weight else 0
    return total_weight, total_cost, per_kg


def all_user_ids():
    """Distinct users who have at least one record — used by the daily reminder job."""
    ids = set()
    with get_conn() as conn:
        for table in ("processes", "debts", "recipes"):
            for row in conn.execute(f"SELECT DISTINCT user_id FROM {table}"):
                ids.add(row["user_id"])
    return list(ids)
