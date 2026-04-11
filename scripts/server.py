#!/usr/bin/env python3
"""
Minimal Python HTTP server + SQLite for AAPK POS Exchange form.
- POST /submit : accepts JSON, inserts into submissions.db
- (Optional) GET /admin, /admin.csv : enable with ENABLE_ADMIN=1

Environment variables (optional):
  - PORT            : default 8080
  - DB_PATH         : default "submissions.db"
  - ENABLE_ADMIN    : "1" to enable /admin and /admin.csv (default "0")
  - ALLOWED_ORIGIN  : CORS origin (default "*"; set to "https://hartung.work" in prod)

Docker-friendly: listens on 0.0.0.0, logs to stdout, graceful SIGTERM shutdown.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import csv
import json
import os
import signal
import sqlite3
import sys
from datetime import datetime
from io import StringIO

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
DB_PATH = os.environ.get("DB_PATH", "submissions.db")
ENABLE_ADMIN = os.environ.get("ENABLE_ADMIN", "0") == "1"
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*")  # e.g., "https..."

# todo add country 
COLUMNS = [
    "id",
    "submitted_at",
    "username",
    "name",
    "address",
    "address2",
    "city",
    "state",
    "zip",
    "email",
]

# ---------- Database helpers ----------

def init_db():
    """Create table if it doesn't exist (idempotent)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
    CREATE TABLE IF NOT EXISTS submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        submitted_at TEXT NOT NULL,
        username TEXT,
        name TEXT,
        address TEXT,
        address2 TEXT,
        city TEXT,
        state TEXT,
        zip TEXT,
        email TEXT
    );
    """)
    conn.commit()
    conn.close()

def save_submission(data: dict):
    """Insert one submission row."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO submissions (
            submitted_at, username, name, address, address2, city, state, zip, email
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data.get("submittedAt"),
            data.get("username"),
            data.get("name"),
            data.get("address"),
            data.get("address2") or "",
            data.get("city"),
            data.get("state"),
            data.get("zip"),
            data.get("email"),
        ),
    )
    conn.commit()
    conn.close()

def fetch_all_submissions():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT {', '.join(COLUMNS)} FROM submissions ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows

# ---------- Small utilities ----------


def html_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )

def render_admin_page(rows):
    styles = """
      body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; margin: 24px; }
      h1 { margin-bottom: 12px; }
      .actions { margin: 8px 0 16px; }
      table { border-collapse: collapse; width: 100%; }
      th, td { border: 1px solid #ddd; padding: 8px; vertical-align: top; }
      th { background: #f5f5f5; position: sticky; top: 0; }
      tr:nth-child(even) { background: #fafafa; }
    """
    head = f"""
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Submissions</title>
      <style>{styles}</style>
    </head>
    """

    header = f"""
      <h1>AAPK POS Exchange — Submissions</h1>
      <div class="actions">
        <a href="/admin.csv"><button type="button">Download CSV</button></a>
        <span style="margin-left:10px;color:#666;">Total: {len(rows)}</span>
      </div>
    """

    ths = "".join(f"<th>{html_escape(col)}</th>" for col in COLUMNS)
    trs = []
    for r in rows:
        tds = []
        for col in COLUMNS:
            val = r[col]
            tds.append(f"<td>{html_escape(val)}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")

    table = f"""
      <table>
        <thead><tr>{ths}</tr></thead>
        <tbody>
          {''.join(trs)}
        </tbody>
      </table>
    """

    return f"<!doctype html><html>{head}<body>{header}{table}</body></html>"

# ---------- HTTP handler ----------

class App(BaseHTTPRequestHandler):
    server_version = "AAPKForm/1.1"

    def log_message(self, fmt, *args):
        # Log to stdout for Docker
        sys.stdout.write("%s - - [%s] %s\n" % (self.address_string(),
                                               datetime.utcnow().isoformat() + "Z",
                                               fmt % args))
        sys.stdout.flush()

    def _set_headers(self, status=200, content_type="application/json", extra_headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        # CORS
        self.send_header("Access-Control-Allow-Origin", ALLOWED_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers()

    def do_GET(self):
        # Health check
        if self.path == "/":
            self._set_headers(200, content_type="text/plain; charset=utf-8")
            self.wfile.write(b"OK")
            return

        # Admin HTML (optional)
        if ENABLE_ADMIN and self.path == "/admin":
            rows = fetch_all_submissions()
            html = render_admin_page(rows)
            self._set_headers(200, content_type="text/html; charset=utf-8")
            self.wfile.write(html.encode("utf-8"))
            return

        # Admin CSV (optional)
        if ENABLE_ADMIN and self.path == "/admin.csv":
            rows = fetch_all_submissions()
            buf = StringIO()
            writer = csv.writer(buf)
            writer.writerow(COLUMNS)
            for r in rows:
                writer.writerow([r[c] for c in COLUMNS])
            data = buf.getvalue().encode("utf-8")
            self._set_headers(
                200,
                content_type="text/csv; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="submissions-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}Z.csv"'
                },
            )
            self.wfile.write(data)
            return

        self._set_headers(404)
        self.wfile.write(b'{"error":"Not found"}')

    def do_POST(self):
        if self.path != "/submit":
            self._set_headers(404)
            self.wfile.write(b'{"error":"Not found"}')
            return

        # Read and parse JSON
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > 1024 * 1024:  # 1MB cap
                self._set_headers(413)
                self.wfile.write(b'{"error":"Payload too large"}')
                return
            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))
        except Exception:
            self._set_headers(400)
            self.wfile.write(b'{"error":"Invalid JSON"}')
            return

        # Minimal server-side validation
        required = ["submittedAt", "username", "name", "address", "city", "state", "zip", "email"]
        missing = [k for k in required if not (data.get(k) or "").strip()]
        if missing:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Missing fields", "fields": missing}).encode("utf-8"))
            return

        try:
            save_submission(data)
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": "DB error", "detail": str(e)}).encode("utf-8"))
            return

        self._set_headers(200)
        self.wfile.write(b'{"ok": true}')

# ---------- Server bootstrap ----------


def serve():
    init_db()
    httpd = HTTPServer((HOST, PORT), App)
    print(
        f"Server listening on {HOST}:{PORT}, DB at {os.path.abspath(DB_PATH)}, admin={'on' if ENABLE_ADMIN else 'off'}",
        flush=True,
    )

    # Graceful shutdown on SIGTERM (docker stop)
    def handle_sigterm(signum, frame):
        print("SIGTERM received, shutting down...", flush=True)
        try:
            httpd.shutdown()
        except Exception:
            pass

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        print("Server stopped.", flush=True)

if __name__ == "__main__":
    serve()
