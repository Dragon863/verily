import asyncio
from aiosmtpd.controller import Controller
from email import message_from_bytes
import re
import sqlite3

conn = sqlite3.connect("codes.db", check_same_thread=False)
cursor = conn.cursor()


def init_db():
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS codes (code TEXT PRIMARY KEY, email TEXT)"
    )
    conn.commit()


def find_first_eight_digit_number(input_string: str) -> str:
    match = re.search(r"\b\d{8}\b", input_string)
    if match:
        return match.group(0)
    return None


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
            "danielbenge@proton.me",
        ]:
            return "550 not relaying from that domain"

        print(envelope.mail_from.split("@")[0])
        print("Message for %s" % envelope.rcpt_tos)
        plain_text_part = None
        email_message = message_from_bytes(envelope.content)
        for part in email_message.walk():
            if part.get_content_type() == "text/plain":
                plain_text_part = part.get_payload(decode=True).decode("utf-8")
                break
        if plain_text_part:
            print("Plain text content:")
            print(plain_text_part)
            code = find_first_eight_digit_number(plain_text_part)
            if code:
                print("Found code:", code)
                cursor.execute(
                    "INSERT INTO codes (code, email) VALUES (?, ?)",
                    (code, envelope.mail_from.split("@")[0]),
                )
                conn.commit()
            else:
                print("No code found")

        return "250 Message accepted for delivery"


init_db()
controller = Controller(MailHandler(), hostname="0.0.0.0", port=25)
controller.start()
asyncio.get_event_loop().run_forever()
