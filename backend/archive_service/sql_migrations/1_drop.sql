-- Historical filename retained for deployment compatibility. This migration
-- must never drop Archive data.
CREATE SCHEMA IF NOT EXISTS memorypal_archive;
SET search_path TO memorypal_archive, public;
