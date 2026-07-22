\set ON_ERROR_STOP on

-- Extensions are installed in public so every application schema can use the
-- same types and functions with explicit qualification where appropriate.
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public;
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;

-- Keep services isolated while sharing one PostgreSQL cluster. This bootstrap
-- creates namespaces only; the migration runner installs the Gateway schema,
-- and the explicit backfill tool copies existing SQLite data.
CREATE SCHEMA IF NOT EXISTS memorypal_gateway AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS memorypal_archive AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS memorypal_vectors AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS memorypal_ops AUTHORIZATION CURRENT_USER;
CREATE SCHEMA IF NOT EXISTS memorypal_meta AUTHORIZATION CURRENT_USER;

CREATE TABLE IF NOT EXISTS memorypal_meta.schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

COMMENT ON SCHEMA memorypal_gateway IS 'Gateway transactional tables and runtime operation state.';
COMMENT ON SCHEMA memorypal_archive IS 'Archive service tables; isolated from Gateway names.';
COMMENT ON SCHEMA memorypal_vectors IS 'Dimension-specific pgvector indexes for RAG and portrait features.';
COMMENT ON SCHEMA memorypal_ops IS 'Read-only operational and admin analytics views over Gateway state.';
