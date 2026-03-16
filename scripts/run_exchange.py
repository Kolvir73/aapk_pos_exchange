#!/usr/bin/env python3
import argparse
import os
import random
import sqlite3
import subprocess
from collections import defaultdict
from email.message import EmailMessage

# ---------- Utilities ----------
def norm_username(u: str) -> str:
    # lower + trim + collapse internal whitespace
    return " ".join((u or "").strip().lower().split())

def connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_history_tables(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS participants_year (
      event_year INTEGER NOT NULL,
      username_norm TEXT NOT NULL,
      real_name TEXT,
      PRIMARY KEY (event_year, username_norm)
    );

    CREATE TABLE IF NOT EXISTS pairings_year (
      event_year INTEGER NOT NULL,
      giver_username_norm TEXT NOT NULL,
      receiver_username_norm TEXT NOT NULL,
      created_at TEXT NOT NULL DEFAULT (DATETIME('now')),
      PRIMARY KEY (event_year, giver_username_norm)
    );

    CREATE INDEX IF NOT EXISTS idx_pairings_year_receiver
      ON pairings_year(event_year, receiver_username_norm);

    CREATE INDEX IF NOT EXISTS idx_pairings_all_giver
      ON pairings_year(giver_username_norm);

    CREATE INDEX IF NOT EXISTS idx_pairings_all_receiver
      ON pairings_year(receiver_username_norm);
    """)

# ---------- Load current submissions and history ----------
def load_current_submissions(conn):
    rows = conn.execute("""
      SELECT username, name, address, address2, city, state, zip, email
      FROM submissions
      WHERE username IS NOT NULL AND TRIM(username) <> ''
    """).fetchall()

    if not rows:
        raise SystemExit("No submissions found (or all are missing username).")

    people = {}
    collisions = defaultdict(list)

    for r in rows:
        raw_u = r["username"]
        u = norm_username(raw_u)
        collisions[u].append(raw_u)

        # keep only the first seen row for that normalized username
        # force admin to resolve normalization collisions explicitly
        if u in people:
            continue

        d = dict(r)
        d["username_norm"] = u
        d["username_raw"] = raw_u
        people[u] = d

    # detect collisions where multiple distinct raw usernames normalize to same key
    bad = {u: raws for u, raws in collisions.items() if len({x.strip() for x in raws}) > 1}
    if bad:
        msg = ["Username normalization collisions detected:"]
        for u, raws in bad.items():
            msg.append(f"  normalized='{u}' from raw values: {sorted({x for x in raws})}")
        raise SystemExit("\n".join(msg))

    return people

def load_history(conn):
    # history[giver][receiver] -> list of years when that directed pairing occurred
    hist = defaultdict(lambda: defaultdict(list))
    rows = conn.execute("""
      SELECT event_year, giver_username_norm, receiver_username_norm
      FROM pairings_year
    """).fetchall()

    for r in rows:
        y = int(r["event_year"])
        g = r["giver_username_norm"]
        rc = r["receiver_username_norm"]
        hist[g][rc].append(y)

    return hist

# ---------- Matching logic ----------
def has_two_cycle(mapping):
    for g, r in mapping.items():
        if mapping.get(r) == g:
            return True
    return False

def is_valid(mapping):
    # no self
    for g, r in mapping.items():
        if g == r:
            return False
    # no 2-cycles if n > 2
    if len(mapping) > 2 and has_two_cycle(mapping):
        return False
    return True

def recency_penalty(years, current_year):
    """
    Penalize repeats; more recent repeats cost more.
    Least-recent repeats cost less.
    """
    if not years:
        return 0.0
    p = 0.0
    for y in years:
        age = max(1, current_year - y)  # 1 => last year
        p += 100.0 / age                # adjust weighting if desired
    return p

def score(mapping, history, current_year):
    """
    Lower score is better. Penalize:
      - direct repeats (giver->receiver)
      - reverse repeats (receiver->giver)
    """
    total = 0.0
    for g, r in mapping.items():
        total += recency_penalty(history[g].get(r, []), current_year)
        total += recency_penalty(history[r].get(g, []), current_year)
    return total

def random_assignment(usernames):
    receivers = usernames[:]
    random.shuffle(receivers)
    return dict(zip(usernames, receivers))

def find_best(usernames, history, year, tries=150000, seed=42):
    if seed is not None and seed != 0:
        random.seed(seed)

    best_map = None
    best_score = float("inf")

    for _ in range(tries):
        m = random_assignment(usernames)
        if not is_valid(m):
            continue
        s = score(m, history, year)
        if s < best_score:
            best_score = s
            best_map = m
            if best_score == 0:
                break

    if best_map is None:
        raise SystemExit("Could not find a valid assignment. Increase --tries or check participants count.")
    return best_map, best_score

# ---------- Persistence ----------
def write_history(conn, year, people, mapping):
    # prevent accidental overwrite
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM pairings_year WHERE event_year=?",
        (year,)
    ).fetchone()["n"]
    if existing:
        raise SystemExit(
            f"Pairings already exist for {year}. Delete rows for that year if you want to regenerate."
        )

    # store username + real name for participants this year
    part_rows = [(year, u, (people[u].get("name") or "").strip()) for u in people]
    conn.executemany("""
      INSERT OR REPLACE INTO participants_year(event_year, username_norm, real_name)
      VALUES (?, ?, ?)
    """, part_rows)

    # store pairings (username only)
    pair_rows = [(year, g, r) for g, r in mapping.items()]
    conn.executemany("""
      INSERT INTO pairings_year(event_year, giver_username_norm, receiver_username_norm)
      VALUES (?, ?, ?)
    """, pair_rows)

# ---------- Emailing ----------
def build_email(year, giver, receiver, subject_prefix):
    msg = EmailMessage()
    msg["Subject"] = f"{subject_prefix} {year}: Your Recipient"
    msg["To"] = (giver.get("email") or "").strip()

    giver_name = (giver.get("name") or giver["username_raw"] or giver["username_norm"]).strip()

    body = (
        f"Hi {giver_name},\n\n"
        f"Thanks for joining the {year} package exchange!\n\n"
        "You will be sending a package to:\n\n"
        f"Name: {receiver.get('name','')}\n"
        f"Address: {receiver.get('address','')}\n"
        f"Address 2: {receiver.get('address2','')}\n"
        f"City/State/ZIP: {receiver.get('city','')}, {receiver.get('state','')} {receiver.get('zip','')}\n"
        f"Email: {receiver.get('email','')}\n\n"
        "Please keep this assignment confidential.\n\n"
        "Happy gifting!\n"
    )
    msg.set_content(body)
    return msg

def send_via_sendmail(msg, from_addr):
    msg["From"] = from_addr
    p = subprocess.Popen(
        ["/usr/sbin/sendmail", "-t", "-i", "-f", from_addr],
        stdin=subprocess.PIPE
    )
    p.communicate(msg.as_bytes())
    if p.returncode != 0:
        raise RuntimeError(f"sendmail failed with return code {p.returncode}")

def send_via_smtp(msg, from_addr):
    import smtplib
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]

    msg["From"] = from_addr
    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)

# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(description="Annual package exchange matcher and email sender")
    ap.add_argument("--db", required=True, help="Path to SQLite DB")
    ap.add_argument("--year", type=int, required=True, help="Event year (e.g., 2026)")
    ap.add_argument("--tries", type=int, default=150000, help="Random search iterations")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed (set to 0 to randomize)")
    ap.add_argument("--mode", choices=["sendmail", "smtp"], default="smtp", help="Email delivery method")
    ap.add_argument("--from-addr", default=os.environ.get("FROM_ADDR", "noreply@example.com"))
    ap.add_argument("--dry-run", action="store_true", help="Do not send emails; just print what would happen")
    ap.add_argument("--subject-prefix", default="Package Exchange")
    args = ap.parse_args()

    with connect(args.db) as conn:
        ensure_history_tables(conn)

        people = load_current_submissions(conn)
        usernames = sorted(people.keys())
        history = load_history(conn)

        mapping, best = find_best(usernames, history, args.year, tries=args.tries, seed=args.seed)
        print(f"Participants: {len(usernames)} | Best score: {best:.2f}")

        write_history(conn, args.year, people, mapping)
        print(f"Saved privacy-safe history for {args.year} (usernames + real names + pairings).")

        for giver_u, receiver_u in mapping.items():
            giver = people[giver_u]
            receiver = people[receiver_u]

            to_addr = (giver.get("email") or "").strip()
            if not to_addr:
                print(f"SKIP (no email for giver): username={giver_u}")
                continue

            msg = build_email(args.year, giver, receiver, args.subject_prefix)

            if args.dry_run:
                print(f"DRY RUN: would send to {to_addr} | {giver_u} -> {receiver_u}")
                continue

            if args.mode == "sendmail":
                send_via_sendmail(msg, args.from_addr)
            else:
                send_via_smtp(msg, args.from_addr)

        print("Done.")

if __name__ == "__main__":
    main()
