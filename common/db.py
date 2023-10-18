import sqlite3

from flask import abort


def get_db_connection():
    conn = sqlite3.connect("db/database.db")
    conn.row_factory = sqlite3.Row
    return conn


def get_comic(comic_id):
    conn = get_db_connection()
    comic = conn.execute("SELECT * FROM comics WHERE id = ?", (comic_id,)).fetchone()
    conn.close()
    if comic is None:
        abort(404)
    return comic
