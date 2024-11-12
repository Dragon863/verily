import asyncio
from aiosmtpd.controller import Controller
from email import message_from_bytes
import re
import sqlite3
from aiohttp import web
import json

class EmailAddress:
    def __init__(self, address: str):
        self.address = address
    
class SenderAddress(EmailAddress):
    def __init__(self, address):
        super().__init__(address)
        self.__validSenders = [
            "noreply@github.com",
            "dragon863.dev@gmail.com"
        ]

    def is_valid(self) -> bool:
        return self.address in self.__validSenders
    
class ReceiverAddress(EmailAddress):
    def __init__(self, address):
        super().__init__(address)
    
    def is_valid(self) -> bool:
        return self.address.endswith("@mail.danieldb.uk") or self.address.endswith("@runshaw.dino.icu")

class Database:
    def __init__(self, filename: str="codes.db"):
        self.__conn = sqlite3.connect(filename, check_same_thread=False)
        self.__cursor = self.__conn.cursor()

    def init_db(self) -> None:
        print("DB init")
        self.__cursor.execute(
            "CREATE TABLE IF NOT EXISTS codes (code TEXT PRIMARY KEY, email TEXT)"
        )
        self.__conn.commit()
        return

    def writeData(self, code: str, email: str) -> None:
        self.__cursor.execute(
            "INSERT OR IGNORE INTO codes (code, email) VALUES (?, ?)",
            (code, email),
        )
        self.__conn.commit()
    
    def fetchCodes(self) -> list:
        self.__cursor.execute("SELECT * FROM codes ORDER BY code DESC LIMIT 10")
        codes = self.__cursor.fetchall()
        return codes
    
db = Database("codes.db")
db.init_db()


def find_first_eight_digit_number(input_string: str) -> str:
    match = re.search(r"\b\d{8}\b", input_string)
    return match.group(0) if match else None


class MailHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        receiver = ReceiverAddress(address=address)
        if not receiver.is_valid():
            print("Receiver does not end with a valid extension")
            return "550 not relaying to that domain"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        sender = SenderAddress(envelope.mail_from)
        if not sender.is_valid():
            print("email from not in allowed list")
            return "550 not relaying from that domain"

        email_message = message_from_bytes(envelope.content)
        plain_text_part = None
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                plain_text_part = part.get_payload(decode=True).decode("utf-8")
                break

        if plain_text_part:
            code = find_first_eight_digit_number(plain_text_part)
            if code:
                firstEmailPart = envelope.rcpt_tos[0].split("@")[0]
                db.writeData(code, firstEmailPart)
                await notify_clients(code, firstEmailPart)

        print("Accepted email")
        return "250 Message accepted for delivery"


connected_clients = set()


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)

    codes = db.fetchCodes()
    await ws.send_str(json.dumps({"initial_codes": codes}))

    try:
        async for msg in ws:
            pass
    finally:
        connected_clients.remove(ws)
    return ws


async def notify_clients(code, email):
    message = json.dumps({"new_code": {"code": code, "email": email}})
    for ws in connected_clients:
        await ws.send_str(message)


async def index(request):
    return web.FileResponse("dashboard.html")


async def init_app():
    app = web.Application()
    app.add_routes(
        [
            web.get("/ws", websocket_handler),  # WebSocket route for live updates
            web.get("/", index),  # Serve the dashboard
        ]
    )
    return app


controller = Controller(MailHandler(), hostname="0.0.0.0", port=25) # 0.0.0.0 is all interfaces, port 25 sometimes needs sudo :/
controller.start()

app = init_app()
web.run_app(app, host="0.0.0.0", port=8080)
asyncio.get_event_loop().run_forever()
