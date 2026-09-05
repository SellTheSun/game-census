-- Canonical enrollment, source capture, and operational ledgers are retained.
CREATE TABLE IF NOT EXISTS schema_migration (
    version integer PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS app (
    app_id bigint PRIMARY KEY CHECK (app_id BETWEEN 1 AND 4294967295),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS tracking_interval (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    app_id bigint NOT NULL REFERENCES app(app_id),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    interval_seconds integer NOT NULL CHECK (interval_seconds BETWEEN 300 AND 604800)
);
CREATE INDEX IF NOT EXISTS tracking_interval_app_time ON tracking_interval(app_id, started_at DESC);
CREATE TABLE IF NOT EXISTS collection_run (
    run_id uuid PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    app_ids jsonb NOT NULL, sources jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS run_completion (
    run_id uuid PRIMARY KEY REFERENCES collection_run(run_id),
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    status text NOT NULL CHECK (status IN ('succeeded','partial','failed')),
    report jsonb NOT NULL
);
CREATE TABLE IF NOT EXISTS request_attempt (
    attempt_id uuid PRIMARY KEY, run_id uuid NOT NULL REFERENCES collection_run(run_id),
    app_id bigint NOT NULL REFERENCES app(app_id), source text NOT NULL,
    host_group text NOT NULL CHECK (host_group IN ('webapi','store')),
    dispatched_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX IF NOT EXISTS request_attempt_quota ON request_attempt(host_group, dispatched_at DESC);
CREATE TABLE IF NOT EXISTS request_result (
    attempt_id uuid PRIMARY KEY REFERENCES request_attempt(attempt_id),
    completed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    status text NOT NULL CHECK (status IN ('succeeded','failed')), http_status integer,
    error jsonb
);
CREATE TABLE IF NOT EXISTS capture (
    capture_id uuid PRIMARY KEY, attempt_id uuid UNIQUE NOT NULL REFERENCES request_attempt(attempt_id),
    run_id uuid NOT NULL REFERENCES collection_run(run_id), app_id bigint NOT NULL REFERENCES app(app_id),
    source text NOT NULL, source_version text NOT NULL,
    request_started_at timestamptz NOT NULL, received_at timestamptz NOT NULL,
    http_status integer NOT NULL, parameters jsonb NOT NULL,
    payload bytea NOT NULL, checksum text NOT NULL CHECK (length(checksum) = 64),
    capture_form text NOT NULL
);
CREATE INDEX IF NOT EXISTS capture_app_time ON capture(app_id, received_at DESC);
-- Rebuildable projections; capture payload and its version own source facts.
CREATE TABLE IF NOT EXISTS player_sample (
    capture_id uuid PRIMARY KEY REFERENCES capture(capture_id), app_id bigint NOT NULL REFERENCES app(app_id),
    observed_at timestamptz NOT NULL, player_count bigint NOT NULL CHECK (player_count >= 0),
    parser_version text NOT NULL
);
CREATE INDEX IF NOT EXISTS player_sample_app_time ON player_sample(app_id, observed_at DESC);
CREATE TABLE IF NOT EXISTS app_name (
    capture_id uuid PRIMARY KEY REFERENCES capture(capture_id), app_id bigint NOT NULL REFERENCES app(app_id),
    observed_at timestamptz NOT NULL, name text NOT NULL, parser_version text NOT NULL
);
CREATE INDEX IF NOT EXISTS app_name_app_time ON app_name(app_id, observed_at DESC);
INSERT INTO schema_migration(version) VALUES (1) ON CONFLICT DO NOTHING;
