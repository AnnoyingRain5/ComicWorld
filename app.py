import sqlite3
from flask import (
    Flask,
    render_template,
    request,
    url_for,
    flash,
    redirect,
    make_response,
)
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv
from functools import wraps
import jwt
from flask_sitemap import Sitemap
from datetime import datetime, timedelta
import upgrade_db
import mimetypes

upgrade_db.upgrade_if_needed()

load_dotenv()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tiff", "webp"}
SITEMAP_URLS = ("index", "login", "artists", "series_list", "rss", "create_account")


def get_db_connection():
    conn = sqlite3.connect("db/database.db")
    conn.row_factory = sqlite3.Row
    return conn


class Artist:
    def __init__(self, dbresp: list):
        self.id: int = dbresp[0]
        self.created_date: datetime = datetime.fromisoformat(dbresp[1])
        self.username: str = dbresp[2]
        self.passhash: str = dbresp[3]
        self.isadmin: bool = bool(dbresp[4])
        self.islocked: bool = bool(dbresp[5])


# decorator for verifying the JWT
def check_token(required: bool = False, adminrequired: bool = False):
    def _check_token(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            # jwt is passed in the request header
            if "token" in request.cookies:
                token = request.cookies["token"]
            # return 401 if token is not passed
            if not token:
                if required:
                    flash("You must be logged in to do that!")
                    return redirect("/login")
                else:
                    return f(None, *args, **kwargs)
            conn = get_db_connection()
            try:
                # decoding the payload to fetch the stored details
                data = jwt.decode(token, app.config["SECRET_KEY"], algorithms=["HS256"])
                artist = conn.execute(
                    "SELECT * FROM artists WHERE id = ?", (data["id"],)
                ).fetchone()
                if Artist(artist).islocked:
                    flash(
                        "Your account has been locked. Please contact AnnoyingRains for assistance."
                    )
                    resp = make_response(redirect("/"))
                    resp.delete_cookie("token")
                    return resp
                if adminrequired:
                    if Artist(artist).isadmin == False:
                        flash("Only adminstrators can access that page.")
                        return redirect("/")
            except jwt.exceptions.ExpiredSignatureError as e:
                if required:
                    flash("Your login has expired! Please log in again")
                    return redirect("/login")
                else:
                    return f(None, *args, **kwargs)
            except jwt.exceptions.PyJWTError:
                if required:
                    flash("You have an invalid token! Please log in again")
                    return redirect("/login")
                else:
                    return f(None, *args, **kwargs)
            # returns the current logged in users context to the routes
            if artist is not None:
                # convert the artist into an artist object
                artist = Artist(artist)
            return f(artist, *args, **kwargs)

        return decorated

    return _check_token


def get_comic(comic_id):
    conn = get_db_connection()
    comic = conn.execute("SELECT * FROM comics WHERE id = ?", (comic_id,)).fetchone()
    conn.close()
    if comic is None:
        abort(404)
    return comic


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


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

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["UPLOAD_FOLDER"] = "static/comics"
app.config["MAX_LOGIN_TIME"] = int(maxlogintime)
ext = Sitemap(app=app)


@app.route("/")
@check_token()
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


@app.route("/<int:comic_id>")
@check_token()
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


@app.route("/artists/<string:artist>")
@check_token()
def artistpage(login_artist, artist):
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


@app.route("/artists/<string:artist>/feed")
def artistrssfeed(artist):
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


@app.route("/testauth")
@check_token(required=True)
def testauth(artist):
    return f"artist: {artist[2]}"


@app.route("/login", methods=["GET", "POST"])
@check_token()
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
            "exp": datetime.utcnow() + timedelta(seconds=app.config["MAX_LOGIN_TIME"]),
        },
        app.config["SECRET_KEY"],
    )
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie(
        "token",
        token,
        max_age=app.config["MAX_LOGIN_TIME"],
        secure=True,
        httponly=True,
        samesite="Strict",
    )
    return resp


@app.route("/logout")
def logout():
    flash("Logged out, this did not invalidate your token!")
    flash(
        "This means, if you were infected by malware, you'll need to contact AnnoyingRains!"
    )
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie("token", "")
    return resp


@app.route("/artists")
@check_token()
def artists(login_artist: Artist | None):
    conn = get_db_connection()
    artists = conn.execute("SELECT username FROM artists").fetchall()
    conn.close()
    return render_template("artists.jinja", artists=artists, login_artist=login_artist)


@app.route("/series")
@check_token()
def series_list(login_artist: Artist | None):
    conn = get_db_connection()
    series = conn.execute("SELECT * FROM series").fetchall()
    conn.close()
    return render_template(
        "series_list.jinja", series_list=series, login_artist=login_artist
    )


@app.route("/series/<string:seriesName>")
@check_token()
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


@app.route("/series/<string:seriesName>/feed")
def seriesrssfeed(seriesName):
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


@app.route("/create_series", methods=("GET", "POST"))
@check_token()
def create_series(login_artist: Artist):
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


@app.route("/create", methods=("GET", "POST"))
@check_token(required=True)
def create(login_artist: Artist):
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
                    return redirect("/create")
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
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
                cur.close()
                conn.close()
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


@app.route("/series/<string:SeriesName>/edit", methods=("GET", "POST"))
@check_token(required=True)
def edit_series(login_artist: Artist, SeriesName):
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


@app.route("/series/<string:SeriesName>/delete", methods=("POST",))
@check_token(required=True)
def delete_series(login_artist: Artist, SeriesName):
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


@app.route("/<int:id>/edit", methods=("GET", "POST"))
@check_token(required=True)
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


@app.route("/create_account", methods=("GET", "POST"))
@check_token()
def create_account(login_artist: Artist):
    if request.method == "POST":
        code = request.form["code"]
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


@app.route("/<int:id>/delete", methods=("POST",))
@check_token(required=True)
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


@app.route("/admin")
@check_token(required=True, adminrequired=True)
def admin(login_artist):
    return render_template("admin_panel.jinja", login_artist=login_artist)


@app.route("/admin/create_signup_code", methods=("POST",))
@check_token(required=True, adminrequired=True)
def create_signup_code(login_artist: Artist):
    conn = get_db_connection()
    code = request.form["code"]
    conn.execute("INSERT INTO codes (code, expired) VALUES (?, ?)", (code, False))
    conn.commit()
    conn.close()
    flash(f'Signup code "{code}" was successfully created!')
    return redirect(url_for("admin"))


@app.route("/admin/create_artist", methods=("POST",))
@check_token(required=True, adminrequired=True)
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
    return redirect(url_for("admin"))


@app.route("/admin/lock_artist", methods=("POST",))
@check_token(required=True, adminrequired=True)
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
    return redirect(url_for("admin"))


@app.route("/admin/unlock_artist", methods=("POST",))
@check_token(required=True, adminrequired=True)
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
    return redirect(url_for("admin"))


@app.route("/admin/delete_artist", methods=("POST",))
@check_token(required=True, adminrequired=True)
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
    return redirect(url_for("admin"))


@app.route("/rss")
@check_token()
def rss(login_artist: Artist):
    return render_template("rss.jinja", login_artist=login_artist)


@app.route("/terms-of-service")
@check_token()
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
        yield "comic", {"comic_id": comic[0]}
    artists = conn.execute(
        "SELECT username FROM artists ORDER BY created DESC"
    ).fetchall()
    for artist in artists:
        yield "artistpage", {"artist": artist[0]}
    series_db = conn.execute("SELECT name FROM series").fetchall()
    for series in series_db:
        yield "series", {"seriesName": series[0]}
