import mimetypes
from flask import (
    Blueprint,
    current_app,
    render_template,
    request,
    make_response,
    flash,
    redirect,
    url_for,
)
from common.auth import check_token
from common.artist import Artist
from common.db import get_db_connection

bp = Blueprint("series", __name__, url_prefix="/series")


@bp.route("/")
@check_token(current_app)
def list(login_artist: Artist | None):
    conn = get_db_connection()
    series = conn.execute("SELECT * FROM series").fetchall()
    conn.close()
    return render_template(
        "series_list.jinja", series_list=series, login_artist=login_artist
    )


@bp.route("/<string:seriesName>")
@check_token(current_app)
def series(login_artist: Artist | None, seriesName: str):
    conn = get_db_connection()
    page = request.args.get("page", type=int)
    if page is None:
        page = 0
    else:
        page -= 1
    offset = page * 50
    seriesID = conn.execute(
        "SELECT id FROM series WHERE name = ?", (seriesName,)
    ).fetchone()
    if seriesID is None:
        flash("Invaid Series!")
        return redirect("/series")
    seriesID = seriesID[0]
    comics = conn.execute(
        "SELECT * FROM comics WHERE seriesid = ? ORDER BY created DESC LIMIT 51 OFFSET ?",
        (seriesID, offset),
    ).fetchall()
    artists = conn.execute("SELECT id, username FROM artists").fetchall()
    # convert the artist to a dict for easy searching
    artistdict = {}
    for other_artist in artists:
        artistdict.update({other_artist[0]: other_artist[1]})
    conn.close()
    # if there are more comics, allow going to the next page
    # and clean up the extra comic
    if len(comics) > 50:
        comics.pop()
        allownext = True
    else:
        # if not, do not allow going to the next page
        allownext = False
    return render_template(
        "series.jinja",
        seriesName=seriesName,
        comics=comics,
        page=page + 1,
        allownext=allownext,
        login_artist=login_artist,
        artists=artistdict,
    )


@bp.route("/<string:seriesName>/feed")
def feed(seriesName):
    conn = get_db_connection()
    series_id = conn.execute(
        "SELECT id FROM series WHERE name = ?", (seriesName,)
    ).fetchone()
    comics = conn.execute(
        "SELECT * FROM comics WHERE seriesid = ? ORDER BY created DESC",
        (series_id[0],),
    ).fetchall()
    artists = conn.execute("SELECT id, username FROM artists").fetchall()
    # convert the artist to a dict for easy searching
    artistdict = {}
    for other_artist in artists:
        artistdict.update({other_artist[0]: other_artist[1]})
    series_db = conn.execute("SELECT id, name FROM series").fetchall()
    seriesdict = {}
    # convert the series to a dict for easy searching
    for series in series_db:
        seriesdict.update({series[0]: series[1]})
    conn.close()
    response = make_response(
        render_template(
            "rss/series.jinja",
            comics=comics,
            seriesName=seriesName,
            artists=artistdict,
            series=seriesdict,
            types_map=mimetypes.types_map,
        )
    )
    response.headers["Content-Type"] = "application/xml"
    return response


@bp.route("/<string:SeriesName>/edit", methods=("GET", "POST"))
@check_token(current_app, required=True)
def edit(login_artist: Artist, SeriesName):
    if request.method == "POST":
        conn = get_db_connection()
        test = conn.execute(
            "SELECT name FROM series WHERE name = ?", (request.form["name"],)
        ).fetchone()
        if test is not None:
            # there is already a series with this name
            flash("There is already a series with this name!")
            return redirect("/edit_series")
        artistid = conn.execute(
            "SELECT artistid FROM series WHERE name = ?", (SeriesName,)
        ).fetchone()[0]
        if artistid == login_artist.id or login_artist.isadmin:
            conn.execute(
                "UPDATE series SET (name) = (?) WHERE name = ?",
                (request.form["name"], SeriesName),
            )
        else:
            flash("You cannot edit other people's series!")
            return redirect("/series")

        conn.commit()
        conn.close()
        flash("Series updated!")
        return redirect(f"/series")
    else:
        return render_template(
            "edit_series.jinja", login_artist=login_artist, SeriesName=SeriesName
        )


@bp.route("/<string:SeriesName>/delete", methods=("POST",))
@check_token(current_app, required=True)
def delete(login_artist: Artist, SeriesName):
    conn = get_db_connection()
    artistid = conn.execute(
        "SELECT artistid FROM series WHERE name = ?", (SeriesName,)
    ).fetchone()[0]
    if login_artist.id == artistid or login_artist.isadmin:
        conn.execute("DELETE FROM series WHERE name = ?", (SeriesName,))
    else:
        flash("You can't delete other people's series!")
        return redirect(url_for("index"))
    conn.commit()
    conn.close()
    flash("Series deleted!")
    return redirect(url_for("index"))
