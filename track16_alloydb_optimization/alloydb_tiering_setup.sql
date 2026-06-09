-- =====================================================================================
-- Track 16: AlloyDB Optimization & Storage Tiering Script
-- Description: Sets up autonomous storage configurations, columnar engine integration,
--              and analytical load routing for AlloyDB.
-- =====================================================================================

-- 1. Enable AlloyDB Columnar Engine and pgvector Extensions
CREATE EXTENSION IF NOT EXISTS google_columnar_engine CASCADE;
CREATE EXTENSION IF NOT EXISTS vector CASCADE;

-- 2. Configure AlloyDB Engine Optimization Parameters (System Level)
-- Note: These parameters are tuned for AlloyDB log-stream decoupling and transactional isolation.
-- Memory allocated to the columnar engine (tuned for OLAP workload scaling)
ALTER SYSTEM SET google_columnar_engine.memory_size_in_mb = 8192;
-- Enable automatic columnar recommendation and populating
ALTER SYSTEM SET google_columnar_engine.auto_columnarization_enabled = on;
-- Set route optimization to prioritize columnar engine scans for complex queries
ALTER SYSTEM SET google_columnar_engine.query_routing_mode = 'RECOMMENDED';

-- 3. Create Operational Schema and Partitioned Storage Layout
CREATE SCHEMA IF NOT EXISTS operational_engines;

-- Base Table designed for range partitioning to optimize storage tiering vector.
-- In AlloyDB, historical partitions are automatically tiered to colder storage tiers.
CREATE TABLE IF NOT EXISTS operational_engines.tower_telemetry_history (
    event_timestamp TIMESTAMP NOT NULL,
    tower_id VARCHAR(50) NOT NULL,
    cell_id VARCHAR(50) NOT NULL,
    traffic_bytes BIGINT NOT NULL,
    packet_count INT NOT NULL,
    threat_severity VARCHAR(10) NOT NULL,
    payload_raw TEXT,
    threat_embedding vector(768)
) PARTITION BY RANGE (event_timestamp);

-- Create an HNSW index for fast vector similarity search
CREATE INDEX ON operational_engines.tower_telemetry_history 
USING hnsw (threat_embedding vector_cosine_ops);

-- 4. Create Active Partitions
CREATE TABLE IF NOT EXISTS operational_engines.telemetry_y2026m06 PARTITION OF operational_engines.tower_telemetry_history
    FOR VALUES FROM ('2026-06-01 00:00:00') TO ('2026-07-01 00:00:00');

CREATE TABLE IF NOT EXISTS operational_engines.telemetry_y2026m07 PARTITION OF operational_engines.tower_telemetry_history
    FOR VALUES FROM ('2026-07-01 00:00:00') TO ('2026-08-01 00:00:00');

-- 5. Register Telemetry Table with AlloyDB Columnar Engine
-- This forces the AlloyDB storage layer to pull these tables into the columnar cache.
SELECT google_columnar_engine_add_table('operational_engines.tower_telemetry_history');

-- 6. Configure Autovacuum Parameters optimized for high-velocity log streaming
-- This prevents table bloat and frees up log buffer space quickly.
ALTER TABLE operational_engines.tower_telemetry_history SET (
    autovacuum_vacuum_scale_factor = 0.05,
    autovacuum_analyze_scale_factor = 0.02,
    autovacuum_vacuum_cost_delay = 2
);

-- 7. Verify Columnar Ingestion Status Query
-- Use this query to monitor memory usage of the decoupled log-stream buffer.
CREATE OR REPLACE VIEW operational_engines.v_columnar_engine_status AS
SELECT 
    relation::regclass AS table_name,
    columns_count,
    blocks_count,
    status AS loading_status
FROM 
    gce_relations;
