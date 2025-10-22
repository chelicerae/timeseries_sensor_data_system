DROP TABLE IF EXISTS sensor_data;

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE sensor_data (
    id SERIAL NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    sensor_id TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL
);
ALTER TABLE sensor_data ADD PRIMARY KEY (id, timestamp);

SELECT create_hypertable('sensor_data', 'timestamp', if_not_exists => TRUE);

-- Continuous aggregate for hourly summaries
CREATE MATERIALIZED VIEW IF NOT EXISTS measurement_hourly
WITH (timescaledb.continuous) AS
SELECT time_bucket('1 hour', timestamp) AS bucket,
       sensor_id,
       AVG(value) AS avg_value,
       MIN(value) AS min_value,
       MAX(value) AS max_value,
       COUNT(*) AS samples
FROM sensor_data
GROUP BY bucket, sensor_id;

-- Reresh policy
SELECT add_continuous_aggregate_policy('measurement_hourly',
    start_offset => INTERVAL '7 days',
    end_offset   => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');