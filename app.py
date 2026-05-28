"""
Household Tracker - Shared todo and grocery list for the local network.

Run:
    python app.py

Then access from any device on your wifi at: http://<your-machine-ip>:5000
"""
import sqlite3
from pathlib import Path
from flask import Flask, render_template, request, jsonify, g

APP_DIR = Path(__file__).parent
DB_PATH = APP_DIR / "tracker.db"

# Each list always has an "Uncategorized" section that can't be deleted.
# When a section is deleted, its items move here instead of being lost.
UNCATEGORIZED_NAME = "Uncategorized"

app = Flask(__name__)


# ---------- Database helpers ----------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """
    Create tables if missing. Also migrate v1 schemas that don't have a
    section_id column yet -- existing items get moved to Uncategorized.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            list_type TEXT NOT NULL CHECK (list_type IN ('todos', 'groceries')),
            name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (list_type, name)
        );

        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS groceries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0,
            section_id INTEGER REFERENCES sections(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Migrate older DBs that don't have section_id on the items tables.
    for table in ("todos", "groceries"):
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if "section_id" not in cols:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN section_id INTEGER "
                f"REFERENCES sections(id) ON DELETE SET NULL"
            )

    # Ensure each list has a default Uncategorized section.
    for list_type in ("todos", "groceries"):
        existing = conn.execute(
            "SELECT id FROM sections WHERE list_type = ? AND is_default = 1",
            (list_type,),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO sections (list_type, name, position, is_default) "
                "VALUES (?, ?, 0, 1)",
                (list_type, UNCATEGORIZED_NAME),
            )

    # Any items with NULL section_id (from migration) go to that list's default.
    for list_type, table in (("todos", "todos"), ("groceries", "groceries")):
        default_id = conn.execute(
            "SELECT id FROM sections WHERE list_type = ? AND is_default = 1",
            (list_type,),
        ).fetchone()[0]
        conn.execute(
            f"UPDATE {table} SET section_id = ? WHERE section_id IS NULL",
            (default_id,),
        )

    conn.commit()
    conn.close()


def get_default_section_id(db, list_type):
    row = db.execute(
        "SELECT id FROM sections WHERE list_type = ? AND is_default = 1",
        (list_type,),
    ).fetchone()
    return row["id"] if row else None


def section_to_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "position": row["position"],
        "is_default": bool(row["is_default"]),
    }


def item_to_dict(row):
    return {
        "id": row["id"],
        "text": row["text"],
        "done": bool(row["done"]),
        "section_id": row["section_id"],
    }


# ---------- Routes ----------

@app.route("/")
def index():
    return render_template("index.html")


# ----- Sections -----

@app.route("/api/<list_type>/sections", methods=["GET"])
def list_sections(list_type):
    if list_type not in ("todos", "groceries"):
        return jsonify({"error": "invalid list"}), 404
    rows = get_db().execute(
        "SELECT id, name, position, is_default FROM sections "
        "WHERE list_type = ? "
        "ORDER BY is_default DESC, position ASC, id ASC",
        (list_type,),
    ).fetchall()
    return jsonify([section_to_dict(r) for r in rows])


@app.route("/api/<list_type>/sections", methods=["POST"])
def add_section(list_type):
    if list_type not in ("todos", "groceries"):
        return jsonify({"error": "invalid list"}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if name.lower() == UNCATEGORIZED_NAME.lower():
        return jsonify({"error": "reserved name"}), 400

    db = get_db()
    dup = db.execute(
        "SELECT id FROM sections WHERE list_type = ? AND LOWER(name) = LOWER(?)",
        (list_type, name),
    ).fetchone()
    if dup:
        return jsonify({"error": "section already exists"}), 409

    next_pos = db.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 AS p FROM sections "
        "WHERE list_type = ? AND is_default = 0",
        (list_type,),
    ).fetchone()["p"]

    cur = db.execute(
        "INSERT INTO sections (list_type, name, position, is_default) "
        "VALUES (?, ?, ?, 0)",
        (list_type, name, next_pos),
    )
    db.commit()
    row = db.execute(
        "SELECT id, name, position, is_default FROM sections WHERE id = ?",
        (cur.lastrowid,),
    ).fetchone()
    return jsonify(section_to_dict(row)), 201


@app.route("/api/<list_type>/sections/<int:section_id>", methods=["PATCH"])
def rename_section(list_type, section_id):
    if list_type not in ("todos", "groceries"):
        return jsonify({"error": "invalid list"}), 404
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    if name.lower() == UNCATEGORIZED_NAME.lower():
        return jsonify({"error": "reserved name"}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, name, position, is_default FROM sections "
        "WHERE id = ? AND list_type = ?",
        (section_id, list_type),
    ).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    if row["is_default"]:
        return jsonify({"error": "can't rename default section"}), 400

    dup = db.execute(
        "SELECT id FROM sections "
        "WHERE list_type = ? AND LOWER(name) = LOWER(?) AND id != ?",
        (list_type, name, section_id),
    ).fetchone()
    if dup:
        return jsonify({"error": "section already exists"}), 409

    db.execute("UPDATE sections SET name = ? WHERE id = ?", (name, section_id))
    db.commit()
    row = db.execute(
        "SELECT id, name, position, is_default FROM sections WHERE id = ?",
        (section_id,),
    ).fetchone()
    return jsonify(section_to_dict(row))


@app.route("/api/<list_type>/sections/<int:section_id>", methods=["DELETE"])
def delete_section(list_type, section_id):
    if list_type not in ("todos", "groceries"):
        return jsonify({"error": "invalid list"}), 404
    db = get_db()
    row = db.execute(
        "SELECT id, is_default FROM sections WHERE id = ? AND list_type = ?",
        (section_id, list_type),
    ).fetchone()
    if row is None:
        return jsonify({"error": "not found"}), 404
    if row["is_default"]:
        return jsonify({"error": "can't delete default section"}), 400

    default_id = get_default_section_id(db, list_type)
    db.execute(
        f"UPDATE {list_type} SET section_id = ? WHERE section_id = ?",
        (default_id, section_id),
    )
    db.execute("DELETE FROM sections WHERE id = ?", (section_id,))
    db.commit()
    return jsonify({"ok": True, "items_moved_to": default_id})


# ----- Items (todos + groceries share logic) -----

def _item_endpoints(list_type):
    table = list_type

    def list_items():
        rows = get_db().execute(
            f"SELECT id, text, done, section_id FROM {table} "
            f"ORDER BY done ASC, id ASC"
        ).fetchall()
        return jsonify([item_to_dict(r) for r in rows])

    def add_item():
        data = request.get_json(silent=True) or {}
        text = (data.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text required"}), 400

        db = get_db()
        section_id = data.get("section_id")
        if section_id is None:
            section_id = get_default_section_id(db, list_type)
        else:
            sec = db.execute(
                "SELECT id FROM sections WHERE id = ? AND list_type = ?",
                (section_id, list_type),
            ).fetchone()
            if sec is None:
                return jsonify({"error": "invalid section_id"}), 400

        cur = db.execute(
            f"INSERT INTO {table} (text, section_id) VALUES (?, ?)",
            (text, section_id),
        )
        db.commit()
        row = db.execute(
            f"SELECT id, text, done, section_id FROM {table} WHERE id = ?",
            (cur.lastrowid,),
        ).fetchone()
        return jsonify(item_to_dict(row)), 201

    def toggle_item(item_id):
        db = get_db()
        row = db.execute(
            f"SELECT id, done FROM {table} WHERE id = ?", (item_id,)
        ).fetchone()
        if row is None:
            return jsonify({"error": "not found"}), 404
        new_done = 0 if row["done"] else 1
        db.execute(f"UPDATE {table} SET done = ? WHERE id = ?", (new_done, item_id))
        db.commit()
        row = db.execute(
            f"SELECT id, text, done, section_id FROM {table} WHERE id = ?",
            (item_id,),
        ).fetchone()
        return jsonify(item_to_dict(row))

    def delete_item(item_id):
        db = get_db()
        cur = db.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        db.commit()
        if cur.rowcount == 0:
            return jsonify({"error": "not found"}), 404
        return jsonify({"ok": True})

    return list_items, add_item, toggle_item, delete_item


for _lt in ("todos", "groceries"):
    _list, _add, _toggle, _delete = _item_endpoints(_lt)
    app.add_url_rule(f"/api/{_lt}", f"{_lt}_list", _list, methods=["GET"])
    app.add_url_rule(f"/api/{_lt}", f"{_lt}_add", _add, methods=["POST"])
    app.add_url_rule(
        f"/api/{_lt}/<int:item_id>/toggle", f"{_lt}_toggle", _toggle, methods=["POST"]
    )
    app.add_url_rule(
        f"/api/{_lt}/<int:item_id>", f"{_lt}_delete", _delete, methods=["DELETE"]
    )


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=False)
