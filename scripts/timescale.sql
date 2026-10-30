-- Optional: convert the telemetry table into a TimescaleDB hypertable.
-- Requires POSTGRES_IMAGE=timescale/timescaledb:latest-pg16 and an existing
-- (possibly empty) telemetry table created by the backend on first start.
-- Timescale requires the partitioning column in every unique index, so the
-- surrogate primary key is widened to (id, utc) first.
CREATE EXTENSION IF NOT EXISTS timescaledb;
ALTER TABLE telemetry DROP CONSTRAINT IF EXISTS telemetry_pkey;
ALTER TABLE telemetry ADD PRIMARY KEY (id, utc);
SELECT create_hypertable('telemetry', 'utc', migrate_data => true, if_not_exists => true);
-- Example retention: keep 90 days of raw housekeeping.
-- SELECT add_retention_policy('telemetry', INTERVAL '90 days');
