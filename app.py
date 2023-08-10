import sqlite3
from flask import Flask, render_template, request, url_for, flash, redirect
from werkzeug.exceptions import abort
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from dotenv import load_dotenv

load_dotenv()

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "tiff", "webp"}


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


def check_auth():
    conn = get_db_connection()
    print(request.form["username"])
    artist = conn.execute(
        "SELECT passhash, id FROM artists WHERE username = ?",
        (request.form["username"],),
    ).fetchone()
    if artist is not None:
        if check_password_hash(artist[0], request.form["password"]):
            return artist
        else:
            return None
    else:
        return None


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["UPLOAD_FOLDER"] = "static/comics"


@app.route("/")
def index():
    conn = get_db_connection()
    comics = conn.execute("SELECT * FROM comics").fetchall()
    artists = conn.execute("SELECT id, username FROM artists").fetchall()
    conn.close()
    artistdict = {}
    for artist in artists:
        artistdict.update({artist[0]: artist[1]})
    return render_template(
        "index.jinja",
        comics=comics,
        artists=artistdict,
        showimages=request.args.get("showimages", type=int),
    )


@app.route("/<int:comic_id>")
def comic(comic_id):
    comic = get_comic(comic_id)
    return render_template("comic.jinja", comic=comic)


@app.route("/artists/<string:artist>")
def artistpage(artist):
    conn = get_db_connection()
    artist_id = conn.execute(
        "SELECT id FROM artists WHERE username = ?", (artist,)
    ).fetchone()
    comics = conn.execute(
        "SELECT * FROM comics WHERE artistid = ?", (artist_id[0],)
    ).fetchall()
    conn.close()
    print(request.args.get("showimages", type=int))
    return render_template(
        "artist.jinja",
        artist=artist,
        comics=comics,
        showimages=request.args.get("showimages", type=int),
    )


@app.route("/artists")
def artists():
    conn = get_db_connection()
    artists = conn.execute("SELECT username FROM artists").fetchall()
    conn.close()
    return render_template("artists.jinja", artists=artists)


@app.route("/create", methods=("GET", "POST"))
def create():
    if request.method == "POST":
        conn = get_db_connection()
        artist = check_auth()
        if artist is None:
            flash("Invalid username or password!")
            return redirect(request.url)
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
                    (title, secure_filename(file.filename.split(".")[-1]), artist[1]),  # type: ignore
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
        return render_template("create.jinja")


@app.route("/<int:id>/edit", methods=("GET", "POST"))
def edit(id):
    comic = get_comic(id)
    if request.method == "POST":
        artist = check_auth()
        if artist is None:
            flash("Incorrect username or password!")
            return redirect(url_for("index"))
        title = request.form["title"]

        if not title:
            flash("Title is required!")
        else:
            conn = get_db_connection()
            artistid = conn.execute(
                "SELECT artistid FROM comics WHERE id = ?", (id,)
            ).fetchone()[0]
            if artist[1] == artistid:
                conn.execute("UPDATE comics SET title = ?" " WHERE id = ?", (title, id))
            else:
                flash("You can't edit other people's comics!")
            conn.commit()
            conn.close()
            return redirect(url_for("index"))

    return render_template("edit.jinja", comic=comic)


@app.route("/create_account", methods=("GET", "POST"))
def create_account():
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
            return redirect(url_for("index"))

    return render_template("create_account.jinja")


@app.route("/<int:id>/delete", methods=("POST",))
def delete(id):
    artist = check_auth()
    if artist is None:
        flash("Incorrect username or password!")
        return redirect(url_for("index"))
    comic = get_comic(id)
    conn = get_db_connection()
    artistid = conn.execute(
        "SELECT artistid FROM comics WHERE id = ?", (id,)
    ).fetchone()[0]
    if artist[1] == artistid:
        conn.execute("DELETE FROM comics WHERE id = ?", (id,))
    else:
        flash("You can't edit other people's comics!")
        return redirect(url_for("index"))
    conn.commit()
    conn.close()
    flash('"{}" was successfully deleted!'.format(comic["title"]))
    return redirect(url_for("index"))
