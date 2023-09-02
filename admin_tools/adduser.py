import sqlite3
from werkzeug.security import generate_password_hash

connection = sqlite3.connect("../db/database.db")
username = input("username: ")
passhash = generate_password_hash(input("password: "))
if input("admin? y or n").lower() == "y":
    admin = True
else:
    admin = False

with open("schema.sql") as f:
    connection.execute(
        "INSERT INTO artists (username, passhash, isadmin) VALUES (?, ?, ?)",
        (username, passhash, admin),
    )


connection.commit()
connection.close()
