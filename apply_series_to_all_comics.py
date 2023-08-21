import sqlite3

connection = sqlite3.connect("db/database.db")
artistid = input(
    "Which artist ID should this be for? If none, leave this blank and just hit enter"
)
seriesname = input("Please provide a name for the series: ")

if artistid == "":
    connection.execute(
        "INSERT INTO series (name) VALUES (?)",
        (seriesname,),
    )
else:
    connection.execute(
        "INSERT INTO series (name, artistid) VALUES (?, ?)",
        (seriesname, artistid),
    )

id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
connection.execute("UPDATE comics SET seriesid = ?", (id,))
connection.commit()
connection.close()
