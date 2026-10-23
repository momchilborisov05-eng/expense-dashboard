"""
Expense Tracker Dashboard - Flask REST API + SQLite + JavaScript frontend.

Run:
    python app.py            # starts on http://localhost:5000
    python app.py --demo     # fills the database with sample data first
"""

import argparse
import os
import random
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request

CATEGORIES = ["Food", "Transport", "Housing", "Entertainment", "Health", "Shopping", "Other"]
DEFAULT_DB = Path(__file__).with_name("expenses.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    description TEXT    NOT NULL,
    amount      REAL    NOT NULL CHECK (amount > 0),
    category    TEXT    NOT NULL,
    spent_on    TEXT    NOT NULL  -- ISO date, YYYY-MM-DD
);
CREATE INDEX IF NOT EXISTS idx_expenses_spent_on ON expenses (spent_on);
"""


def create_app(db_path: Path = DEFAULT_DB) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = str(db_path)

    def get_db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DB_PATH"])
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with closing(sqlite3.connect(app.config["DB_PATH"])) as conn:
        conn.executescript(SCHEMA)

    def error(message: str, status: int = 400):
        return jsonify({"error": message}), status

    def validate(data: dict) -> tuple[dict | None, str | None]:
        """Check an expense from the client. Returns (clean_data, error_message)."""
        description = str(data.get("description", "")).strip()
        if not description:
            return None, "Description is required."
        if len(description) > 200:
            return None, "Description is too long (max 200 characters)."
        try:
            amount = round(float(data.get("amount")), 2)
        except (TypeError, ValueError):
            return None, "Amount must be a number."
        if amount <= 0:
            return None, "Amount must be greater than 0."
        category = data.get("category")
        if category not in CATEGORIES:
            return None, f"Category must be one of: {', '.join(CATEGORIES)}."
        try:
            spent_on = date.fromisoformat(str(data.get("spent_on"))).isoformat()
        except ValueError:
            return None, "Date must be in the format YYYY-MM-DD."
        return {"description": description, "amount": amount,
                "category": category, "spent_on": spent_on}, None

    @app.get("/")
    def index():
        return render_template("index.html", categories=CATEGORIES)

    @app.get("/api/expenses")
    def list_expenses():
        query = "SELECT * FROM expenses"
        params = []
        if category := request.args.get("category"):
            query += " WHERE category = ?"
            params.append(category)
        query += " ORDER BY spent_on DESC, id DESC LIMIT 200"
        rows = get_db().execute(query, params).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.post("/api/expenses")
    def add_expense():
        clean, message = validate(request.get_json(silent=True) or {})
        if message:
            return error(message)
        db = get_db()
        cursor = db.execute(
            "INSERT INTO expenses (description, amount, category, spent_on) "
            "VALUES (:description, :amount, :category, :spent_on)",
            clean,
        )
        db.commit()
        return jsonify({"id": cursor.lastrowid, **clean}), 201

    @app.put("/api/expenses/<int:expense_id>")
    def update_expense(expense_id: int):
        clean, message = validate(request.get_json(silent=True) or {})
        if message:
            return error(message)
        db = get_db()
        cursor = db.execute(
            "UPDATE expenses SET description = :description, amount = :amount, "
            "category = :category, spent_on = :spent_on WHERE id = :id",
            {**clean, "id": expense_id},
        )
        db.commit()
        if cursor.rowcount == 0:
            return error("Expense not found.", 404)
        return jsonify({"id": expense_id, **clean})

    @app.delete("/api/expenses/<int:expense_id>")
    def delete_expense(expense_id: int):
        db = get_db()
        cursor = db.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
        db.commit()
        if cursor.rowcount == 0:
            return error("Expense not found.", 404)
        return "", 204

    @app.get("/api/stats")
    def stats():
        """Aggregated data for the dashboard cards and charts."""
        db = get_db()
        totals = db.execute(
            """SELECT COUNT(*) AS count,
                      COALESCE(SUM(amount), 0) AS total,
                      COALESCE(SUM(CASE WHEN strftime('%Y-%m', spent_on) = strftime('%Y-%m', 'now')
                                        THEN amount END), 0) AS this_month
               FROM expenses"""
        ).fetchone()
        by_category = db.execute(
            """SELECT category, ROUND(SUM(amount), 2) AS total
               FROM expenses GROUP BY category ORDER BY total DESC"""
        ).fetchall()
        by_month = db.execute(
            """SELECT strftime('%Y-%m', spent_on) AS month, ROUND(SUM(amount), 2) AS total
               FROM expenses
               WHERE spent_on >= date('now', 'start of month', '-11 months')
               GROUP BY month ORDER BY month"""
        ).fetchall()
        return jsonify({
            "count": totals["count"],
            "total": round(totals["total"], 2),
            "this_month": round(totals["this_month"], 2),
            "by_category": [dict(r) for r in by_category],
            "by_month": [dict(r) for r in by_month],
        })

    return app


def seed_demo_data(db_path: Path, count: int = 150) -> None:
    """Insert random sample expenses from the last 6 months."""
    samples = {
        "Food": ["Groceries", "Lunch", "Pizza", "Coffee", "Restaurant"],
        "Transport": ["Metro card", "Taxi", "Fuel", "Train ticket"],
        "Housing": ["Rent", "Electricity", "Internet", "Water"],
        "Entertainment": ["Cinema", "Concert", "Streaming subscription", "Video game"],
        "Health": ["Pharmacy", "Gym membership", "Dentist"],
        "Shopping": ["Clothes", "Headphones", "Books", "Shoes"],
        "Other": ["Gift", "Haircut", "Phone bill"],
    }
    ranges = {"Housing": (40, 450), "Shopping": (15, 180), "Health": (10, 90)}
    today = date.today()
    rows = []
    for _ in range(count):
        category = random.choice(CATEGORIES)
        low, high = ranges.get(category, (3, 60))
        rows.append((
            random.choice(samples[category]),
            round(random.uniform(low, high), 2),
            category,
            (today - timedelta(days=random.randint(0, 180))).isoformat(),
        ))
    with closing(sqlite3.connect(db_path)) as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO expenses (description, amount, category, spent_on) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    print(f"Added {count} demo expenses.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="add sample data before starting")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    # The debug reloader runs this file twice; seed only in the first (parent) process.
    if args.demo and not os.environ.get("WERKZEUG_RUN_MAIN"):
        seed_demo_data(DEFAULT_DB)
    create_app().run(debug=True, port=args.port)
