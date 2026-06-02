-- Parent-child chunking support
-- Adds parent_id and chunk_type columns to document_chunks

ALTER TABLE public.document_chunks
  ADD COLUMN IF NOT EXISTS parent_id text;

ALTER TABLE public.document_chunks
  ADD COLUMN IF NOT EXISTS chunk_type text;

CREATE INDEX IF NOT EXISTS idx_document_chunks_parent_id
  ON public.document_chunks(parent_id)
  WHERE parent_id IS NOT NULL;
