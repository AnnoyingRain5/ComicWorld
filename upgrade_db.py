import sqlite3


def upgrade_if_needed():
    connection = sqlite3.connect('db/database.db')
    version: int = connection.execute("SELECT * FROM pragma_user_version").fetchone()[0]
    if version < 1:
        # v0 to v1
        print(f"upgrading from v{version} to v1!")
        connection.execute("CREATE TABLE IF NOT EXISTS series (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL)")
        connection.execute("ALTER TABLE comics ADD COLUMN seriesid INTEGER REFERENCES series(id)")
        connection.execute("PRAGMA user_version = 1")
    if version < 2:
        # v2 to v3
        print(f"upgrading from v{version} to v2!")
        connection.execute("ALTER TABLE series ADD COLUMN artistid INTEGER REFERENCES artist(id)")
        connection.execute("PRAGMA user_version = 2")
    if version < 3:
        print(f"Upgrading from v{version} to v3!")
        connection.execute("ALTER TABLE artists ADD COLUMN islocked BOOLEAN NOT NULL DEFAULT 0")
        connection.execute("PRAGMA user_version = 3")
    connection.commit()
    connection.close()

if __name__ == "__main__":
    upgrade_if_needed()