import sqlite3
from werkzeug.security import generate_password_hash

connection = sqlite3.connect('database.db')
code = input("code: ")

with open('schema.sql') as f:
    connection.execute("INSERT INTO codes (code, expired) VALUES (?, ?)", (code, False))


connection.commit()
connection.close()