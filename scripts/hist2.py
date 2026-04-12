import csv, sqlite3, sys, unicodedata
from datetime import datetime

# read old history from csv file.
CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "POS_hist.csv"
DB_PATH = sys.argv[2] if len(sys.argv) > 2 else "pos_history.db"
TABLE_USERS = "users"
TABLE_SENDS = "sends"

def normalize(u: str) -> str:
    if u is None: return ""
    s = str(u).strip()
    s = unicodedata.normalize("NFC", s)
    s = " ".join(s.split())
    return s.lower()

def setup_db(conn):
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_USERS} (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username_raw TEXT NOT NULL UNIQUE,
        username_norm TEXT NOT NULL UNIQUE
    )""")
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE_SENDS} (
        send_id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_year INTEGER NOT NULL,
        sender_id INTEGER NOT NULL,
        receiver_id INTEGER NOT NULL,
        message_count INTEGER NOT NULL DEFAULT 1,
        first_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(event_year, sender_id, receiver_id)
    )""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sends_sender_receiver ON {TABLE_SENDS}(sender_id, receiver_id)")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_sends_year_sender ON {TABLE_SENDS}(event_year, sender_id)")
    conn.commit()

def get_or_create_user(conn, raw):
    norm = normalize(raw)
    cur = conn.execute(f"SELECT user_id FROM {TABLE_USERS} WHERE username_norm = ?", (norm,))
    row = cur.fetchone()
    if row:
        return row[0]
    cur = conn.execute(f"INSERT INTO {TABLE_USERS} (username_raw, username_norm) VALUES (?, ?)", (raw, norm))
    conn.commit()
    return cur.lastrowid

def import_csv(conn, csv_path):
    with open(csv_path, newline='', encoding='utf-8') as fh:
        reader = csv.reader(fh)
        header = next(reader)
        if len(header) < 2:
            raise SystemExit("CSV must have sender column plus year columns")
        year_cols = header[1:]
        # map header year strings to ints where possible
        years = []
        for h in year_cols:
            h = h.strip()
            if h == "":
                years.append(None)
                continue
            digits = "".join(ch for ch in h if ch.isdigit())
            years.append(int(digits) if digits else None)

        insert_sql = f"""INSERT INTO {TABLE_SENDS}
            (event_year, sender_id, receiver_id, message_count, first_seen)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(event_year, sender_id, receiver_id) DO UPDATE SET
              message_count = {TABLE_SENDS}.message_count + excluded.message_count
        """

        batch = []
        BATCH = 500
        now = datetime.utcnow().isoformat()
        for row in reader:
            if not row or all(c.strip() == "" for c in row):
                continue
            # pad short rows
            if len(row) < len(header):
                row += [""] * (len(header) - len(row))
            sender_raw = row[0]
            sender_id = get_or_create_user(conn, sender_raw)
            for i, y in enumerate(years, start=1):
                if y is None:
                    continue
                recv_raw = row[i] if i < len(row) else ""
                if recv_raw.strip() == "":
                    continue
                receiver_id = get_or_create_user(conn, recv_raw)
                batch.append((y, sender_id, receiver_id, 1, now))
                if len(batch) >= BATCH:
                    conn.executemany(insert_sql, batch)
                    conn.commit()
                    batch.clear()
        if batch:
            conn.executemany(insert_sql, batch)
            conn.commit()

def main():
    conn = sqlite3.connect(DB_PATH)
    setup_db(conn)
    import_csv(conn, CSV_PATH)
    conn.close()
    print("Done.")

if __name__ == "__main__":
    main()
