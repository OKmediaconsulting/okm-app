"""
Jarvis — Gmail Tools
Read and send emails via IMAP/SMTP with App Password.
"""

import imaplib
import smtplib
import email as email_lib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header

GMAIL_USER = "info@okmediaconsulting.net"
GMAIL_APP_PASSWORD = "sqnlolkubumglgty"

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _decode_str(value: str) -> str:
    parts = decode_header(value)
    result = ""
    for part, enc in parts:
        if isinstance(part, bytes):
            result += part.decode(enc or "utf-8", errors="ignore")
        else:
            result += part
    return result


def read_emails(max_results: int = 5, unread_only: bool = True) -> list[dict]:
    """Return list of recent emails with sender, subject, snippet."""
    mail = imaplib.IMAP4_SSL(IMAP_HOST)
    mail.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    mail.select("inbox")

    criteria = "UNSEEN" if unread_only else "ALL"
    _, data = mail.search(None, criteria)
    ids = data[0].split()
    ids = ids[-max_results:][::-1]

    emails = []
    for uid in ids:
        _, msg_data = mail.fetch(uid, "(RFC822)")
        msg = email_lib.message_from_bytes(msg_data[0][1])
        subject = _decode_str(msg.get("Subject", "(kein Betreff)"))
        sender = _decode_str(msg.get("From", "Unbekannt"))
        date = msg.get("Date", "")

        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                    break
        else:
            body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")

        emails.append({
            "from": sender,
            "subject": subject,
            "date": date,
            "snippet": body[:300].strip(),
        })

    mail.logout()
    return emails


def send_email(to: str, subject: str, body: str) -> bool:
    """Send an email via SMTP. Returns True on success."""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, to, msg.as_string())
    return True
