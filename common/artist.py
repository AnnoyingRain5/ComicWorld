from datetime import datetime


class Artist:
    def __init__(self, dbresp: list):
        self.id: int = dbresp[0]
        self.created_date: datetime = datetime.fromisoformat(dbresp[1])
        self.username: str = dbresp[2]
        self.passhash: str = dbresp[3]
        self.isadmin: bool = bool(dbresp[4])
        self.islocked: bool = bool(dbresp[5])
