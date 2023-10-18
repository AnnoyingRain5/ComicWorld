import os
import requests
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
from werkzeug.utils import secure_filename

bp = Blueprint("create", __name__, url_prefix="/create")


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in current_app.config["ALLOWED_EXTENSIONS"]
    )


@bp.route("/comic", methods=("GET", "POST"))
@check_token(current_app, required=True)
def comic(login_artist: Artist):
    if request.method == "POST":
        conn = get_db_connection()
        title = request.form["title"]
        # check if the post request has the file part
        if "image" not in request.files:
            flash("No file part")
            return redirect(request.url)
        file = request.files["image"]
        # check to see if an empty file part is uploaded
        # as some browsers upload an empty file part when none is selected
        if file.filename == "":
            flash("No selected file")
            return redirect(request.url)

        if file and allowed_file(file.filename):
            if not title:
                flash("Title is required!")
                return redirect(request.url)
            else:
                cur = conn.cursor()
                artistid = cur.execute(
                    "SELECT artistid FROM series WHERE name = ?",
                    (request.form["series"],),
                ).fetchone()
                try:
                    artistid = artistid[0]
                except:
                    artistid = None
                # if artistid is None, allow anyone to post to the series
                if login_artist.id != artistid and artistid is not None:
                    flash("You cannot add your comic to someone else's series!")
                    return redirect(url_for("create.comic"))
                # actually add to the database
                if artistid is not None:
                    seriesid = cur.execute(
                        "SELECT id FROM series WHERE name = ?",
                        (request.form["series"],),
                    ).fetchone()[0]
                else:
                    seriesid = None
                cur.execute(
                    "INSERT INTO comics (title, fileext, artistid, seriesid) VALUES (?, ?, ?, ?)",
                    (title, secure_filename(file.filename.split(".")[-1]), login_artist.id, seriesid),  # type: ignore
                )
                conn.commit()
                filename = f"{cur.lastrowid}.{secure_filename(file.filename.split('.')[-1])}"  # type: ignore
                file.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
                cur.close()
                conn.close()
                webhookURL = os.getenv("DISCORD_WEBHOOK_URL")
                print(webhookURL)
                if webhookURL is not None:
                    requests.post(
                        webhookURL,
                        json={
                            "username": login_artist.username,
                            "embeds": [
                                {
                                    "title": title,
                                    "url": f"{current_app.config['SERVER_ADDRESS']}/{cur.lastrowid}",
                                    "description": "Uploaded a new comic",
                                    "image": {
                                        "url": f"{current_app.config['SERVER_ADDRESS']}/static/comics/{filename}"
                                    },
                                }
                            ],
                        },
                    )
                return redirect(url_for("index"))
        else:
            flash(
                "You either did not attach a file, or the file extension was not allowed."
            )
            return redirect(request.url)
    else:
        conn = get_db_connection()
        series = conn.execute("SELECT name FROM series").fetchall()
        conn.commit()
        conn.close()
        return render_template("create.jinja", series=series, login_artist=login_artist)


@bp.route("/series", methods=("GET", "POST"))
@check_token(current_app)
def series(login_artist: Artist):
    if request.method == "POST":
        conn = get_db_connection()
        test = conn.execute(
            "SELECT name FROM series WHERE name = ?", (request.form["name"],)
        ).fetchone()
        if test is not None:
            # there is already a series with this name
            flash("There is already a series with this name!")
            return redirect("/create_series")
        conn.execute(
            "INSERT INTO series (name, artistid) VALUES (?, ?)",
            (request.form["name"], login_artist.id),
        )
        conn.commit()
        conn.close()
        flash("Series created! You can now publish comics to it!")
        return redirect("/")
    else:
        return render_template("create_series.jinja", login_artist=login_artist)
