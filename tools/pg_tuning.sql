-- ============================================================
-- PostgreSQL 17 Performance Tuning for N8N
-- Machine: 64GB RAM, Windows
-- Created: 2026-05-19
-- ============================================================

-- Memory: allocate ~4GB shared buffers (1/16 of total RAM)
ALTER SYSTEM SET shared_buffers = '4GB';

-- Working memory per operation (sorting, hashing)
ALTER SYSTEM SET work_mem = '64MB';

-- Maintenance operations (VACUUM, CREATE INDEX)
ALTER SYSTEM SET maintenance_work_mem = '512MB';

-- Effective cache size (tell planner how much OS cache is available)
ALTER SYSTEM SET effective_cache_size = '48GB';

-- WAL configuration for write-heavy workloads
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = '0.9';
ALTER SYSTEM SET max_wal_size = '2GB';
ALTER SYSTEM SET min_wal_size = '512MB';

-- Connection settings (match N8N pool size)
ALTER SYSTEM SET max_connections = '50';

-- Random page cost (lower for SSD)
ALTER SYSTEM SET random_page_cost = '1.1';
ALTER SYSTEM SET effective_io_concurrency = '200';

-- Parallel query (leverage multiple cores)
ALTER SYSTEM SET max_parallel_workers_per_gather = '4';
ALTER SYSTEM SET max_worker_processes = '8';
ALTER SYSTEM SET max_parallel_workers = '8';
ALTER SYSTEM SET max_parallel_maintenance_workers = '4';

-- Logging (minimal for performance)
ALTER SYSTEM SET log_min_duration_statement = '1000';
ALTER SYSTEM SET log_checkpoints = 'on';

-- Autovacuum tuning (aggressive for N8N execution data)
ALTER SYSTEM SET autovacuum_max_workers = '4';
ALTER SYSTEM SET autovacuum_naptime = '30s';
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = '0.05';
ALTER SYSTEM SET autovacuum_analyze_scale_factor = '0.025';

-- JIT compilation (helps complex queries)
ALTER SYSTEM SET jit = 'on';
