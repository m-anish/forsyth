-- Assembly tracker for build.forsyth.starstucklab.com (Cloudflare D1).
-- People are identified by the email Cloudflare Access signs them in with.

CREATE TABLE IF NOT EXISTS builds (
  id       TEXT PRIMARY KEY,
  name     TEXT NOT NULL,
  owner    TEXT NOT NULL,            -- email
  created  TEXT NOT NULL
);

-- Who may see or change a build. The owner has a row too (role 'owner').
CREATE TABLE IF NOT EXISTS members (
  build    TEXT NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
  email    TEXT NOT NULL,
  role     TEXT NOT NULL CHECK (role IN ('owner', 'editor', 'viewer')),
  added_by TEXT NOT NULL,
  added    TEXT NOT NULL,
  PRIMARY KEY (build, email)
);
CREATE INDEX IF NOT EXISTS members_by_email ON members (email);

-- One row per thing a builder records: a step, a printed part, a hardware item.
CREATE TABLE IF NOT EXISTS items (
  build      TEXT NOT NULL REFERENCES builds(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('steps', 'parts', 'hw')),
  key        TEXT NOT NULL,
  body       TEXT NOT NULL,
  updated    TEXT NOT NULL,
  updated_by TEXT NOT NULL,
  PRIMARY KEY (build, kind, key)
);
