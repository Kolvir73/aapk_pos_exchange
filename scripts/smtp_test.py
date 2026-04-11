#!/usr/bin/env python3
import os
import smtplib
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

smtp_host = os.environ["SMTP_HOST"]
smtp_port = int(os.environ.get("SMTP_PORT", "465"))
smtp_user = os.environ["SMTP_USER"]
smtp_pass = os.environ["SMTP_PASS"]
from_addr = os.environ.get("FROM_ADDR", smtp_user)
to_addr = os.environ.get("TO_ADDR", from_addr)  # send to yourself by default

msg = EmailMessage()
msg["Subject"] = "SMTP connectivity test"
msg["From"] = from_addr
msg["To"] = to_addr
msg.set_content("If you received this, SMTP is working.")

with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as s:
    s.set_debuglevel(1)
    s.login(smtp_user, smtp_pass)
    s.send_message(msg)

# with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
#     s.set_debuglevel(1)
#     s.starttls()
#     s.login(smtp_user, smtp_pass)
#     s.send_message(msg)

print(f"Sent test email to {to_addr}")
