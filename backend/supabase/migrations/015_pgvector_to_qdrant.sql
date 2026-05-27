-- Migration 015: Remove pgvector, keep FTS-only document_chunks
-- Vector operations have moved to Qdrant. This migration cleans up the pgvector artifacts.

-- Drop vector search RPC functions (replaced by Qdrant)
DROP FUNCTION IF EXISTS match_documents(vector(768), uuid, int, float);
DROP FUNCTION IF EXISTS match_documents_filtered(vector(768), uuid, int, float, text[], text);
DROP FUNCTION IF EXISTS hybrid_search(vector(768), text, uuid, int, int);

-- Drop vector index
DROP INDEX IF EXISTS idx_document_chunks_embedding;

-- Remove embedding column
ALTER TABLE public.document_chunks DROP COLUMN IF EXISTS embedding;

-- The following remain unchanged:
-- - document_chunks table (id, user_id, document_id, content, chunk_index, metadata, fts, created_at)
-- - search_chunks_fts RPC function
-- - update_chunk_fts() trigger (trg_chunk_fts)
-- - GIN indexes (idx_document_chunks_fts, idx_document_chunks_metadata)
-- - RLS policies
-- - Other indexes (idx_document_chunks_user, idx_document_chunks_document)
