-- Bristol Bus Pulse - Database Initialization
-- Run this after database creation with PostGIS extension

-- Create UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create schema
CREATE SCHEMA IF NOT EXISTS bristol;

-- Set search path
SET search_path TO bristol, public;

-- Create tables (SQLAlchemy will handle this with ORM)
-- This file is supplementary for manual setup

-- Enable PostGIS functions
SELECT postgis_version();

-- Create indexes for common queries
CREATE INDEX IF NOT EXISTS idx_vehicle_route_delay 
  ON bristol.vehicles(route_id, delay_seconds DESC) 
  WHERE timestamp > now() - interval '1 hour';

CREATE INDEX IF NOT EXISTS idx_vehicle_timestamp 
  ON bristol.vehicles(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_vehicle_position 
  ON bristol.vehicles USING GIST(position);

CREATE INDEX IF NOT EXISTS idx_tripupdate_timestamp 
  ON bristol.trip_updates(timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_route_stats_window 
  ON bristol.route_statistics(route_id, window_start, window_end);

CREATE INDEX IF NOT EXISTS idx_stop_stats_window 
  ON bristol.stop_statistics(stop_id, window_start, window_end);

CREATE INDEX IF NOT EXISTS idx_feed_status_feed_name 
  ON bristol.feed_status(feed_name);

-- Create materialized view for recent delays
CREATE MATERIALIZED VIEW IF NOT EXISTS bristol.recent_route_delays AS
SELECT 
    route_id,
    operator_code,
    COUNT(*) as vehicle_count,
    AVG(COALESCE(delay_seconds, 0)) as avg_delay,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_seconds) as median_delay,
    COUNT(CASE WHEN delay_seconds > 60 THEN 1 END) as delayed_count,
    COUNT(CASE WHEN delay_seconds > 600 THEN 1 END) as severely_delayed_count,
    MAX(timestamp) as last_update
FROM bristol.vehicles
WHERE timestamp > now() - interval '1 hour'
GROUP BY route_id, operator_code;

CREATE INDEX IF NOT EXISTS idx_recent_route_delays_avg_delay
  ON bristol.recent_route_delays(avg_delay DESC);

-- Create materialized view for stop status
CREATE MATERIALIZED VIEW IF NOT EXISTS bristol.stop_status AS
SELECT 
    s.stop_id,
    s.stop_name,
    COUNT(DISTINCT v.route_id) as routes_serving,
    s.position,
    AVG(tu.delay_seconds) as avg_arrival_delay
FROM bristol.stops s
LEFT JOIN bristol.vehicles v ON ST_DWithin(s.position, v.position, 0.001)
LEFT JOIN bristol.trip_updates tu ON tu.trip_id = v.trip_id
WHERE tu.timestamp > now() - interval '1 hour'
GROUP BY s.stop_id, s.stop_name, s.position;

-- Create partition for historical data (optional, for very large deployments)
-- This allows efficient archival of old data
CREATE TABLE IF NOT EXISTS bristol.vehicle_positions_archive PARTITION OF bristol.vehicles
  FOR VALUES FROM ('2020-01-01') TO ('2024-01-01');

-- Grant permissions to app user
GRANT USAGE ON SCHEMA bristol TO bristol_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA bristol TO bristol_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA bristol TO bristol_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA bristol GRANT ALL ON TABLES TO bristol_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA bristol GRANT ALL ON SEQUENCES TO bristol_user;
