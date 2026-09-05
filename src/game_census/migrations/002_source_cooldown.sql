-- Retain upstream Retry-After decisions so another manual run cannot bypass them.
CREATE TABLE IF NOT EXISTS source_cooldown (
    cooldown_id uuid PRIMARY KEY,
    attempt_id uuid UNIQUE NOT NULL REFERENCES request_attempt(attempt_id),
    host_group text NOT NULL CHECK (host_group IN ('webapi','store')),
    recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS source_cooldown_host_expiry ON source_cooldown(host_group, expires_at DESC);
INSERT INTO schema_migration(version) VALUES (2) ON CONFLICT DO NOTHING;
