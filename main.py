import asyncio
from aiosmtpd.controller import Controller
from email import message_from_bytes
import re
import sqlite3
from aiohttp import web
import json

conn = sqlite3.connect("codes.db", check_same_thread=False)
cursor = conn.cursor()


def init_db():
    print("DB init")
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS codes (code TEXT PRIMARY KEY, email TEXT)"
    )
    conn.commit()


def find_first_eight_digit_number(input_string: str) -> str:
    match = re.search(r"\b\d{8}\b", input_string)
    return match.group(0) if match else None


class MailHandler:
    async def handle_RCPT(self, server, session, envelope, address, rcpt_options):
        if not address.endswith("@mail.danieldb.uk"):
            print("Address does not end with @mail.danieldb.uk")
            return "550 not relaying to that domain"
        envelope.rcpt_tos.append(address)
        return "250 OK"

    async def handle_DATA(self, server, session, envelope):
        if not envelope.mail_from in [
            "noreply@github.com",
            "dragon863.dev@gmail.com",
        ]:
            print("Mail from not in allowed list")
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
                cursor.execute(
                    "INSERT OR IGNORE INTO codes (code, email) VALUES (?, ?)",
                    (code, envelope.rcpt_tos.split("@")[0]),
                )
                conn.commit()
                await notify_clients(code, envelope.rcpt_tos.split("@")[0])

        return "250 Message accepted for delivery"


connected_clients = set()


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    connected_clients.add(ws)

    cursor.execute("SELECT * FROM codes ORDER BY code DESC LIMIT 10")
    codes = cursor.fetchall()
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
            web.get("/", index),  # Serve the HTML page
        ]
    )
    return app


init_db()
controller = Controller(MailHandler(), hostname="0.0.0.0", port=25)
controller.start()

app = init_app()
web.run_app(app, host="0.0.0.0", port=8080)
asyncio.get_event_loop().run_forever()
