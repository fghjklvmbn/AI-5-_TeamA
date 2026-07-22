\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS memorypal_vectors.embedding_models (
    id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
    provider text NOT NULL,
    model_name text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    distance_metric text NOT NULL DEFAULT 'cosine' CHECK (distance_metric IN ('cosine', 'inner_product', 'l2')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (provider, model_name, dimensions),
    UNIQUE (id, dimensions)
);

-- Remote Nomic-compatible embeddings are standardized at 768 dimensions.
-- Store source text in the authoritative Gateway tables, not in vector metadata.
CREATE TABLE IF NOT EXISTS memorypal_vectors.embedding_records_768 (
    id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
    model_id uuid NOT NULL,
    model_dimensions integer NOT NULL DEFAULT 768 CHECK (model_dimensions = 768),
    user_id uuid NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    chunk_index integer NOT NULL DEFAULT 0 CHECK (chunk_index >= 0),
    content_hash text NOT NULL,
    embedding public.vector(768) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (model_id, user_id, source_type, source_id, chunk_index),
    FOREIGN KEY (model_id, model_dimensions)
        REFERENCES memorypal_vectors.embedding_models(id, dimensions),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_embedding_records_768_cosine
    ON memorypal_vectors.embedding_records_768
    USING hnsw (embedding public.vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_embedding_records_768_source
    ON memorypal_vectors.embedding_records_768 (user_id, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_embedding_records_768_created_brin
    ON memorypal_vectors.embedding_records_768 USING brin (created_at);

-- The deterministic local Korean hash fallback currently produces 384 values.
-- It lives in a separate table because distances across different dimensions
-- or embedding methods are not meaningful and must never be mixed.
CREATE TABLE IF NOT EXISTS memorypal_vectors.embedding_records_384 (
    id uuid PRIMARY KEY DEFAULT public.gen_random_uuid(),
    model_id uuid NOT NULL,
    model_dimensions integer NOT NULL DEFAULT 384 CHECK (model_dimensions = 384),
    user_id uuid NOT NULL,
    source_type text NOT NULL,
    source_id text NOT NULL,
    chunk_index integer NOT NULL DEFAULT 0 CHECK (chunk_index >= 0),
    content_hash text NOT NULL,
    embedding public.vector(384) NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (model_id, user_id, source_type, source_id, chunk_index),
    FOREIGN KEY (model_id, model_dimensions)
        REFERENCES memorypal_vectors.embedding_models(id, dimensions),
    CHECK (jsonb_typeof(metadata) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_embedding_records_384_cosine
    ON memorypal_vectors.embedding_records_384
    USING hnsw (embedding public.vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_embedding_records_384_source
    ON memorypal_vectors.embedding_records_384 (user_id, source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_embedding_records_384_created_brin
    ON memorypal_vectors.embedding_records_384 USING brin (created_at);

COMMENT ON TABLE memorypal_vectors.embedding_records_768 IS
    '768-dimensional remote-model vector space; compare only rows from a compatible model.';
COMMENT ON TABLE memorypal_vectors.embedding_records_384 IS
    '384-dimensional deterministic fallback vector space; never compare with 768-dimensional rows.';
COMMENT ON COLUMN memorypal_vectors.embedding_records_768.metadata IS
    'Allowlisted chunk metadata only; raw source content remains in its authoritative protected store.';
COMMENT ON COLUMN memorypal_vectors.embedding_records_384.metadata IS
    'Allowlisted feature metadata only; raw conversation content is prohibited.';

COMMIT;
