-- alloydb_scann_migration.sql
-- Production Migration Script: Migrating from pgvector HNSW to AlloyDB ScaNN

-- 1. Setup Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS alloydb_pg_extension;

-- 2. Drop Old HNSW Index (if exists)
DROP INDEX IF EXISTS document_embeddings_hnsw_idx;

-- 3. Create Document Embeddings Table (768-Dimension Vector for Vertex AI Embeddings)
CREATE TABLE IF NOT EXISTS document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id VARCHAR(255) NOT NULL,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding vector(768) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Create AlloyDB ScaNN Index
-- ScaNN uses Anisotropic Vector Quantization to reduce memory usage and write amplification.
-- Parameters:
--   num_leaves: Number of partitions for Voronoi cells. Typically set to sqrt(total_rows) up to 2*sqrt(total_rows).
--   quantizer: Quantization format. 'SQ8' (Scalar Quantization 8-bit) compresses floating-point vectors by 4x.
CREATE INDEX IF NOT EXISTS document_embeddings_scann_idx 
ON document_embeddings 
USING alloydb_scann (embedding vector_cosine_ops)
WITH (num_leaves = 512, quantizer = 'SQ8');

-- 5. Query Tuning Parameters
-- Set the number of leaves to search during query execution. Higher values increase recall but increase latency.
SET alloydb_scann.query_search_leaves = 32;

-- 6. Example Query: Semantic Vector Search (Cosine Similarity)
-- Cosine distance operator is '<=>' in pgvector/AlloyDB
PREPARE semantic_search(vector(768), INT) AS
SELECT 
    id, 
    document_id, 
    content, 
    1 - (embedding <=> $1) AS cosine_similarity
FROM 
    document_embeddings
ORDER BY 
    embedding <=> $1
LIMIT $2;

-- 7. Index Maintenance and Statistics Update
-- Force statistics update to optimize query planner choices
ANALYZE document_embeddings;

-- Query index build status and metadata
SELECT * FROM pg_stat_user_indexes WHERE indexrelname = 'document_embeddings_scann_idx';
