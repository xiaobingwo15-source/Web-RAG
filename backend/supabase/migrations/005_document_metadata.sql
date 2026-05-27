-- Add metadata JSONB column to document_chunks
ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}';

-- GIN index for JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_metadata ON public.document_chunks USING gin(metadata);

-- Add top-level metadata to documents table
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}';

-- Filtered similarity search RPC with metadata filters
CREATE OR REPLACE FUNCTION match_documents_filtered(
  query_embedding vector(768),
  match_user_id uuid,
  match_count int DEFAULT 5,
  similarity_threshold float DEFAULT 0.3,
  filter_tags text[] DEFAULT NULL,
  filter_language text DEFAULT NULL
)
RETURNS TABLE (id uuid, document_id uuid, content text, similarity float, metadata jsonb)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT dc.id, dc.document_id, dc.content,
    1 - (dc.embedding <=> query_embedding) AS similarity,
    dc.metadata
  FROM document_chunks dc
  WHERE dc.user_id = match_user_id
    AND 1 - (dc.embedding <=> query_embedding) > similarity_threshold
    AND (filter_tags IS NULL OR dc.metadata->'tags' ?| filter_tags)
    AND (filter_language IS NULL OR dc.metadata->>'language' = filter_language)
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
