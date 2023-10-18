import os
from flask import (
    Blueprint,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from common.auth import check_token
from common.artist import Artist
from common.db import get_db_connection
from werkzeug.security import generate_password_hash

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@check_token(current_app, required=True, adminrequired=True)
def admin(login_artist):
    return render_template("admin_panel.jinja", login_artist=login_artist)


@bp.route("/create_signup_code", methods=("POST",))
@check_token(current_app, required=True, adminrequired=True)
def create_signup_code(login_artist: Artist):
    conn = get_db_connection()
    code = request.form["code"]
    conn.execute("INSERT INTO codes (code, expired) VALUES (?, ?)", (code, False))
    conn.commit()
    conn.close()
    flash(f'Signup code "{code}" was successfully created!')
    return redirect(url_for("admin.admin"))


@bp.route("/create_artist", methods=("POST",))
@check_token(current_app, required=True, adminrequired=True)
def create_artist(login_artist: Artist):
    conn = get_db_connection()
    username = request.form["username"]
    passhash = generate_password_hash(request.form["password"])
    try:
        isadmin = request.form["isadmin"]
    except:
        isadmin = False
    conn.execute(
        "INSERT INTO artists (username, passhash, isadmin) VALUES (?, ?, ?)",
        (username, passhash, isadmin),
    )
    conn.commit()
    conn.close()
    flash(f'Artist "{username}" was successfully created!')
    return redirect(url_for("admin.admin"))


@bp.route("/lock_artist", methods=("POST",))
@check_token(current_app, required=True, adminrequired=True)
def lock_artist(login_artist: Artist):
    conn = get_db_connection()
    username = request.form["username"]
    conn.execute(
        "UPDATE artists SET islocked = 1 WHERE username = ?",
        (username,),
    )
    conn.commit()
    conn.close()
    flash(f'Artist "{username}" was successfully locked!')
    return redirect(url_for("admin.admin"))


@bp.route("/unlock_artist", methods=("POST",))
@check_token(current_app, required=True, adminrequired=True)
def unlock_artist(login_artist: Artist):
    conn = get_db_connection()
    username = request.form["username"]
    conn.execute(
        "UPDATE artists SET islocked = 0 WHERE username = ?",
        (username,),
    )
    conn.commit()
    conn.close()
    flash(f'Artist "{username}" was successfully unlocked!')
    return redirect(url_for("admin.admin"))


@bp.route("/delete_artist", methods=("POST",))
@check_token(current_app, required=True, adminrequired=True)
def delete_artist(login_artist: Artist):
    conn = get_db_connection()
    username = request.form["username"]
    artistid = conn.execute(
        "SELECT id FROM artists WHERE username = ?", (username,)
    ).fetchone()[0]
    comics = conn.execute(
        "SELECT id, fileext FROM comics WHERE artistid = ?",
        (artistid,),
    ).fetchall()
    for comic in comics:
        try:
            os.remove(f"static/comics/{comic[0]}.{comic[1]}")
        except Exception as e:
            flash(str(e))

    conn.execute(
        "DELETE FROM comics WHERE artistid = ?",
        (artistid,),
    )
    conn.execute(
        "DELETE FROM series WHERE artistid = ?",
        (artistid,),
    )
    conn.execute(
        "DELETE FROM artists WHERE id = ?",
        (artistid,),
    )
    conn.commit()
    conn.close()
    flash(f'Artist "{username}" was successfully deleted.')
    return redirect(url_for("admin.admin"))
