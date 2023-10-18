from flask import Blueprint, current_app, render_template, request, make_response
from common.auth import check_token
from common.artist import Artist
from common.db import get_db_connection
import mimetypes

bp = Blueprint("artists", __name__, url_prefix="/artists")


@bp.route("/")
@check_token(current_app)
def list(login_artist: Artist | None):
    conn = get_db_connection()
    artists = conn.execute("SELECT username FROM artists").fetchall()
    conn.close()
    return render_template("artists.jinja", artists=artists, login_artist=login_artist)


@bp.route("/<string:artist>")
@check_token(current_app)
def artist(login_artist, artist):
    conn = get_db_connection()
    page = request.args.get("page", type=int)
    if page is None:
        page = 0
    else:
        page -= 1
    offset = page * 50
    artist_id = conn.execute(
        "SELECT id FROM artists WHERE username = ?", (artist,)
    ).fetchone()
    comics = conn.execute(
        "SELECT * FROM comics WHERE artistid = ? ORDER BY created DESC LIMIT 51 OFFSET ?",
        (artist_id[0], offset),
    ).fetchall()
    series_db = conn.execute("SELECT id, name FROM series").fetchall()
    seriesdict = {}
    # convert the series to a dict for easy searching
    for series in series_db:
        seriesdict.update({series[0]: series[1]})
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
        "artist.jinja",
        artist=artist,
        comics=comics,
        page=page + 1,
        allownext=allownext,
        series=seriesdict,
        login_artist=login_artist,
    )


@bp.route("/<string:artist>/feed")
def feed(artist):
    conn = get_db_connection()
    artist_id = conn.execute(
        "SELECT id FROM artists WHERE username = ?", (artist,)
    ).fetchone()
    comics = conn.execute(
        "SELECT * FROM comics WHERE artistid = ? ORDER BY created DESC",
        (artist_id[0],),
    ).fetchall()
    series_db = conn.execute("SELECT id, name FROM series").fetchall()
    seriesdict = {}
    # convert the series to a dict for easy searching
    for series in series_db:
        seriesdict.update({series[0]: series[1]})
    artists = conn.execute("SELECT id, username FROM artists").fetchall()
    # convert the artist to a dict for easy searching
    artistdict = {}
    for other_artist in artists:
        artistdict.update({other_artist[0]: other_artist[1]})
    conn.close()
    response = make_response(
        render_template(
            "rss/artist.jinja",
            artist=artist,
            comics=comics,
            series=seriesdict,
            artists=artistdict,
            types_map=mimetypes.types_map,
        )
    )
    response.headers["Content-Type"] = "application/xml"
    return response
