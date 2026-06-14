-- Migration 034: Add per-chunk structural metadata columns
-- Phase 1 of RAG Enhancement Plan: Fix the Structural Metadata Leak
--
-- Adds columns that the chunker already computes but were previously discarded:
--   heading, heading_level, structural_type, page_start, page_end, table_id, breadcrumb_path

ALTER TABLE document_chunks
    ADD COLUMN IF NOT EXISTS heading TEXT DEFAULT '',
    ADD COLUMN IF NOT EXISTS heading_level INT DEFAULT 0,
    ADD COLUMN IF NOT EXISTS structural_type TEXT DEFAULT 'text',
    ADD COLUMN IF NOT EXISTS page_start INT,
    ADD COLUMN IF NOT EXISTS page_end INT,
    ADD COLUMN IF NOT EXISTS table_id TEXT,
    ADD COLUMN IF NOT EXISTS breadcrumb_path JSONB DEFAULT '[]'::jsonb;

-- Index for filtered retrieval by structural type (e.g., "retrieve all tables")
CREATE INDEX IF NOT EXISTS idx_document_chunks_structural_type
    ON document_chunks (structural_type);

-- Index for page-based queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_page_start
    ON document_chunks (page_start) WHERE page_start IS NOT NULL;

-- Index for table-specific retrieval
CREATE INDEX IF NOT EXISTS idx_document_chunks_table_id
    ON document_chunks (table_id) WHERE table_id IS NOT NULL;
