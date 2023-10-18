from flask import (
    Flask,
    render_template,
    request,
    redirect,
    make_response,
)
import os
from dotenv import load_dotenv
from flask_sitemap import Sitemap
from common.auth import check_token
from common.artist import Artist
import upgrade_db
import mimetypes
import subprocess
from common.db import get_db_connection

import blueprints.admin
import blueprints.artists
import blueprints.auth
import blueprints.comics
import blueprints.series
import blueprints.create


upgrade_db.upgrade_if_needed()

load_dotenv()

SITEMAP_URLS = (
    "index",
    "auth.login",
    "artists.list",
    "series.list",
    "rss",
    "auth.create_account",
)


maxlogintime = os.getenv("MAX_LOGIN_TIME")
if maxlogintime is not None:
    if not maxlogintime.isnumeric():
        print("invalid config!")
        exit()
else:
    print("invalid config!")
    exit()
if os.getenv("SECRET_KEY") is None:
    print("invalid config!")
    exit()

if os.getenv("SERVER_ADDRESS") is None:
    print("invalid config!")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["UPLOAD_FOLDER"] = "static/comics"
app.config["MAX_LOGIN_TIME"] = int(maxlogintime)
app.config["ALLOWED_EXTENSIONS"] = ("png", "jpg", "jpeg", "gif", "tiff", "webp")
app.config["SERVER_ADDRESS"] = os.getenv("SERVER_ADDRESS")
ext = Sitemap(app=app)


@app.context_processor
def inject_version_info():
    return dict(
        COMMIT_ID=subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"]
        ).decode(),
        VERSION=subprocess.check_output(
            ["git", "describe", "--tags", "--abbrev=0"]
        ).decode(),
    )


app.register_blueprint(blueprints.admin.bp)
app.register_blueprint(blueprints.artists.bp)
app.register_blueprint(blueprints.auth.bp)
app.register_blueprint(blueprints.comics.bp)
app.register_blueprint(blueprints.create.bp)
app.register_blueprint(blueprints.series.bp)


@app.route("/")
@check_token(app)
def index(login_artist: Artist | None):
    conn = get_db_connection()
    page = request.args.get("page", type=int)
    if page is None:
        page = 0
    else:
        page -= 1
    # pages are 50 items long
    offset = page * 50
    # request one more comic than we need, purely to see if it exists
    comics = conn.execute(
        "SELECT * FROM comics ORDER BY created DESC LIMIT 51 OFFSET ?",
        (offset,),
    ).fetchall()
    # if there are more comics, allow going to the next page
    # and clean up the extra comic
    if len(comics) > 50:
        comics.pop()
        allownext = True
    else:
        # if not, do not allow going to the next page
        allownext = False
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
    return render_template(
        "index.jinja",
        comics=comics,
        artists=artistdict,
        series=seriesdict,
        page=page + 1,
        allownext=allownext,
        login_artist=login_artist,
    )


@app.route("/feed")
def indexrssfeed():
    conn = get_db_connection()
    comics = conn.execute("SELECT * FROM comics ORDER BY created DESC").fetchall()
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
            "rss/index.jinja",
            comics=comics,
            series=seriesdict,
            artists=artistdict,
            types_map=mimetypes.types_map,
        )
    )
    response.headers["Content-Type"] = "application/xml"
    return response


@app.route("/rss")
@check_token(app)
def rss(login_artist: Artist):
    return render_template("rss.jinja", login_artist=login_artist)


@app.route("/terms-of-service")
@check_token(app)
def tos(login_artist: Artist):
    return render_template("terms-of-service.jinja", login_artist=login_artist)


@app.route("/toggletheme")
def toggletheme():
    if request.referrer is not None:
        resp = make_response(redirect(request.referrer))
    else:
        resp = make_response(redirect("/"))
    if request.cookies.get("darkmode", default=None) is None:
        resp.set_cookie("darkmode", "true")
    else:
        resp.delete_cookie("darkmode")
    return resp


@ext.register_generator
def sitemap():
    for page in SITEMAP_URLS:
        yield page, {}
    conn = get_db_connection()
    comics = conn.execute("SELECT id FROM comics ORDER BY created DESC").fetchall()
    for comic in comics:
        yield "comics.comic", {"comic_id": comic[0]}
    artists = conn.execute(
        "SELECT username FROM artists ORDER BY created DESC"
    ).fetchall()
    for artist in artists:
        yield "artists.artist", {"artist": artist[0]}
    series_db = conn.execute("SELECT name FROM series").fetchall()
    for series in series_db:
        yield "series.series", {"seriesName": series[0]}
