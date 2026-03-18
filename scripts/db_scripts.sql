-- Existing table (your form already writes here)
-- (Shown for reference only — do not drop/alter)
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

-- Privacy-safe history: only username + real name per year
CREATE TABLE IF NOT EXISTS participants_year (
  event_year INTEGER NOT NULL,
  username_norm TEXT NOT NULL,
  real_name TEXT,
  PRIMARY KEY (event_year, username_norm)
);

-- Pairings per year (only usernames)
CREATE TABLE IF NOT EXISTS pairings_year (
  event_year INTEGER NOT NULL,
  sender_username_norm TEXT NOT NULL,
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
