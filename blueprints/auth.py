import jwt
from flask import (
    Blueprint,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from common.auth import check_token
from common.artist import Artist
from common.db import get_db_connection
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/testauth")
@check_token(current_app, required=True)
def testauth(artist):
    return f"artist: {artist[2]}"


@bp.route("/create_account", methods=("GET", "POST"))
@check_token(current_app)
def create_account(login_artist: Artist):
    if request.method == "POST":
        code = request.form["code"]
        try:
            request.form["ToS"]
        except:
            flash("You must agree to the Terms of Service!")
            return render_template("create_account.jinja", login_artist=login_artist)
        if not code:
            flash("You need an invite code to join!")
        else:
            conn = get_db_connection()
            expired = conn.execute(
                "SELECT expired FROM codes WHERE code = ?", (request.form["code"],)
            ).fetchone()[0]
            if expired == False:
                passhash = generate_password_hash(request.form["password"])
                conn.execute(
                    "INSERT INTO artists (username, passhash, isadmin) VALUES (?, ?, ?)",
                    (request.form["username"], passhash, False),
                )
                conn.execute(
                    "UPDATE codes SET expired = ? WHERE code = ?", (True, code)
                )
            else:
                flash("Invalid code")
                return redirect(url_for("index"))
            conn.commit()
            conn.close()
            flash("Account created!")
            resp = make_response(redirect(url_for("index")))
            resp.set_cookie("token", "")
            return resp

    return render_template("create_account.jinja", login_artist=login_artist)


@bp.route("/login", methods=["GET", "POST"])
@check_token(current_app)
def login(login_artist: Artist | None):
    if request.method == "GET":
        return render_template("login.jinja", login_artist=login_artist)
    # try to login:
    conn = get_db_connection()
    artist = conn.execute(
        "SELECT passhash, id FROM artists WHERE username = ?",
        (request.form["username"],),
    ).fetchone()

    if artist is None:
        flash("Invalid username or password!")
        return redirect("login")
    if check_password_hash(artist[0], request.form["password"]) == False:
        flash("Invalid username or password!")
        return redirect("login")

    # if we made it this far, the username and password is valid!
    token = jwt.encode(
        {
            "id": artist[1],
            "exp": datetime.utcnow()
            + timedelta(seconds=current_app.config["MAX_LOGIN_TIME"]),
        },
        current_app.config["SECRET_KEY"],
    )
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie(
        "token",
        token,
        max_age=current_app.config["MAX_LOGIN_TIME"],
        secure=True,
        httponly=True,
        samesite="Strict",
    )
    return resp


@bp.route("/logout")
def logout():
    flash("Logged out, this did not invalidate your token!")
    flash(
        "This means, if you were infected by malware, you'll need to contact AnnoyingRains!"
    )
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("token", "")
    return resp
