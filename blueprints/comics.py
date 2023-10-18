import os
from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    flash,
    redirect,
    url_for,
)
from common.auth import check_token
from common.artist import Artist
from common.db import get_db_connection
from common.db import get_comic

bp = Blueprint("comics", __name__, url_prefix="/comics")


@bp.route("/<int:comic_id>")
@check_token(current_app)
def comic(login_artist: Artist, comic_id):
    comic = get_comic(comic_id)
    conn = get_db_connection()
    artist = conn.execute(
        "SELECT username FROM artists WHERE id = ?", (comic[4],)
    ).fetchone()
    if comic["seriesid"]:
        series = conn.execute(
            "SELECT name FROM series WHERE id = ?", (comic["seriesid"],)
        ).fetchone()[0]
    else:
        series = None

    # find the next comic ID depending on the previous page
    if request.args.get("via", default=None) is not None:
        referrer = request.args.get("via")
    else:
        if request.referrer:
            referrer = request.referrer.split("/")[3]
        else:
            referrer = None
    match referrer:
        case "series":
            nextcomic = conn.execute(
                "SELECT id FROM comics WHERE seriesid = ? AND id > ? LIMIT 1",
                (comic["seriesid"], comic["id"]),
            ).fetchone()
            previouscomic = conn.execute(
                "SELECT id FROM comics WHERE seriesid = ? AND id < ? ORDER BY id DESC LIMIT 1",
                (comic["seriesid"], comic["id"]),
            ).fetchone()
        case "artists":
            nextcomic = conn.execute(
                "SELECT id FROM comics WHERE artistid = ? AND id > ? LIMIT 1",
                (comic["artistid"], comic["id"]),
            ).fetchone()
            previouscomic = conn.execute(
                "SELECT id FROM comics WHERE artistid = ? AND id < ? ORDER BY id DESC LIMIT 1",
                (comic["artistid"], comic["id"]),
            ).fetchone()
        case _ if referrer is not None and (
            referrer.startswith("?") or referrer == "index" or referrer == ""
        ):
            nextcomic = conn.execute(
                "SELECT id FROM comics WHERE id > ? LIMIT 1",
                (comic["id"],),
            ).fetchone()
            previouscomic = conn.execute(
                "SELECT id FROM comics WHERE id < ? ORDER BY id DESC LIMIT 1",
                (comic["id"],),
            ).fetchone()
            referrer = "index"
        case _:
            nextcomic = None
            previouscomic = None

    if nextcomic is not None:
        nextcomic = nextcomic[0]

    if previouscomic is not None:
        previouscomic = previouscomic[0]

    return render_template(
        "comic.jinja",
        comic=comic,
        artist=artist[0],
        series=series,
        nextcomic=nextcomic,
        previouscomic=previouscomic,
        referrer=referrer,
        login_artist=login_artist,
    )


@bp.route("/<int:id>/edit", methods=("GET", "POST"))
@check_token(current_app, required=True)
def edit(login_artist: Artist, id):
    comic = get_comic(id)
    if request.method == "POST":
        title = request.form["title"]
        if not title:
            flash("Title is required!")
        else:
            conn = get_db_connection()
            artistid = conn.execute(
                "SELECT artistid FROM comics WHERE id = ?", (id,)
            ).fetchone()[0]
            if login_artist.id == artistid or login_artist.isadmin:
                # all checks passed, update the database
                if request.form["series"] != "None":
                    seriesid = conn.execute(
                        "SELECT id FROM series WHERE name = ?",
                        (request.form["series"],),
                    ).fetchone()[0]
                    conn.execute(
                        "UPDATE comics SET (title, seriesid) = (?, ?)" " WHERE id = ?",
                        (title, seriesid, id),
                    )
                else:
                    # this comic is not in a series
                    conn.execute(
                        "UPDATE comics SET (title, seriesid) = (?, ?)" " WHERE id = ?",
                        (title, None, id),
                    )
            else:
                flash("You can't edit other people's comics!")
            conn.commit()
            conn.close()
            return redirect(url_for("index"))
    conn = get_db_connection()
    series = conn.execute("SELECT name FROM series").fetchall()
    conn.commit()
    conn.close()
    return render_template(
        "edit.jinja", comic=comic, series=series, login_artist=login_artist
    )


@bp.route("/<int:id>/delete", methods=("POST",))
@check_token(current_app, required=True)
def delete(login_artist: Artist, id):
    comic = get_comic(id)
    conn = get_db_connection()
    artistid = conn.execute(
        "SELECT artistid FROM comics WHERE id = ?", (id,)
    ).fetchone()[0]
    if login_artist.id == artistid or login_artist.isadmin:
        fileext = conn.execute(
            "SELECT fileext FROM comics WHERE id = ?", (id,)
        ).fetchone()[0]
        os.remove(f"static/comics/{id}.{fileext}")
        conn.execute("DELETE FROM comics WHERE id = ?", (id,))
    else:
        flash("You can't delete other people's comics!")
        return redirect(url_for("index"))
    conn.commit()
    conn.close()
    flash('"{}" was successfully deleted!'.format(comic["title"]))
    return redirect(url_for("index"))
