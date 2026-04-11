import sqlite3
from email.message import EmailMessage

SENT_FILE = "input.txt"      # addresses that succeeded
SUB_DB = "../db/submissions.db"          # contains submissions table
HIST_DB = "pos_history.db"
YEAR = 2026

# load sent set
with open(SENT_FILE) as f:
    sent = {line.strip().lower() for line in f if line.strip()}

# load submissions (email keyed by normalized username)
def norm(u): return " ".join((u or "").strip().lower().split())

subs = {}
with sqlite3.connect(SUB_DB) as c:
    c.row_factory = sqlite3.Row
    for r in c.execute("SELECT username, name, address, address2, city, state, zip, country, email FROM submissions"):
        if not r["username"] or not r["email"]:
            continue
        subs[norm(r["username"])] = dict(r)

# load history mapping for the year (sender_norm -> receiver_norm)
mapping = {}
with sqlite3.connect(HIST_DB) as c:
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT u_s.username_norm AS sender_norm, u_r.username_norm AS receiver_norm
        FROM sends s
        JOIN users u_s ON s.sender_id = u_s.user_id
        JOIN users u_r ON s.receiver_id = u_r.user_id
        WHERE s.event_year = ?
    """, (YEAR,)).fetchall()
    for r in rows:
        mapping[r["sender_norm"]] = r["receiver_norm"]

# invert mapping to look up by sender email
failed_senders = []
for sender_norm, receiver_norm in mapping.items():
    sender = subs.get(sender_norm)
    if not sender:
        # missing submission info
        failed_senders.append((sender_norm, None, receiver_norm))
        continue
    email = (sender.get("email") or "").strip().lower()
    if email not in sent:
        failed_senders.append((sender_norm, email, receiver_norm))

print("Failed count:", len(failed_senders))
for s_norm, s_email, r_norm in failed_senders:
    print(s_norm, s_email, "->", r_norm)
    # build/resend email here using your existing build_email/send functions
