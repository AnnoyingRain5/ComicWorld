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
from datetime import datetime, timedelta

load_dotenv()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tiff", "webp"}


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


# decorator for verifying the JWT
def check_token(required: bool = False):
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
                print("got here!")
                print(artist)
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
    conn.close()
    # convert the artist to a dict for easy searching
    artistdict = {}
    for other_artist in artists:
        artistdict.update({other_artist[0]: other_artist[1]})
    return render_template(
        "index.jinja",
        comics=comics,
        artists=artistdict,
        page=page + 1,
        allownext=allownext,
        login_artist=login_artist,
    )


@app.route("/<int:comic_id>")
@check_token()
def comic(login_artist: Artist, comic_id):
    comic = get_comic(comic_id)
    conn = get_db_connection()
    artist = conn.execute(
        "SELECT username FROM artists WHERE id = ?", (comic[4],)
    ).fetchone()
    return render_template(
        "comic.jinja", comic=comic, artist=artist[0], login_artist=login_artist
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
    conn.close()
    # if there are more comics, allow going to the next page
    # and clean up the extra comic
    if len(comics) > 50:
        comics.pop()
        allownext = True
    else:
        # if not, do not allow going to the next page
        allownext = False
    print(request.args.get("showimages", type=int))
    return render_template(
        "artist.jinja",
        artist=artist,
        comics=comics,
        page=page + 1,
        allownext=allownext,
        login_artist=login_artist,
    )


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
    flash("This means, if you were infected by malware, you'll need to contact AnnoyingRains!")
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
                # actually add to the database
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO comics (title, fileext, artistid) VALUES (?, ?, ?)",
                    (title, secure_filename(file.filename.split(".")[-1]), login_artist.id),  # type: ignore
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
        return render_template("create.jinja", login_artist=login_artist)


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
            if login_artist.id == artistid:
                conn.execute("UPDATE comics SET title = ?" " WHERE id = ?", (title, id))
            else:
                flash("You can't edit other people's comics!")
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

    return render_template("edit.jinja", comic=comic, login_artist=login_artist)


@app.route("/create_account", methods=("GET", "POST"))
@check_token()
def create_account(login_artist: Artist):
    if request.method == "POST":
        code = request.form["code"]
        if not code:
            flash("You need an invite code to join!")
        else:
            conn = get_db_connection()
            print(request.form["code"])
            expired = conn.execute(
                "SELECT expired FROM codes WHERE code = ?", (request.form["code"],)
            ).fetchone()[0]
            print(expired)
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
    if login_artist.id == artistid:
        conn.execute("DELETE FROM comics WHERE id = ?", (id,))
    else:
        flash("You can't delete other people's comics!")
        return redirect(url_for("index"))
    conn.commit()
    conn.close()
    flash('"{}" was successfully deleted!'.format(comic["title"]))
    return redirect(url_for("index"))
