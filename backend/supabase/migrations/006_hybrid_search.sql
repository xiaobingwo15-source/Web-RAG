-- Add tsvector column for full-text search on document_chunks
ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS fts tsvector;

-- Create GIN index for full-text search
CREATE INDEX IF NOT EXISTS idx_document_chunks_fts ON public.document_chunks USING gin(fts);

-- Populate tsvector for existing chunks
UPDATE public.document_chunks SET fts = to_tsvector('english', content) WHERE fts IS NULL;

-- Trigger to auto-update tsvector on insert/update
CREATE OR REPLACE FUNCTION update_chunk_fts()
RETURNS trigger AS $$
BEGIN
  NEW.fts := to_tsvector('english', NEW.content);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunk_fts ON public.document_chunks;
CREATE TRIGGER trg_chunk_fts
  BEFORE INSERT OR UPDATE ON public.document_chunks
  FOR EACH ROW EXECUTE FUNCTION update_chunk_fts();

-- Full-text search RPC function
CREATE OR REPLACE FUNCTION search_chunks_fts(
  search_query text,
  match_user_id uuid,
  match_count int DEFAULT 10
)
RETURNS TABLE (id uuid, document_id uuid, content text, rank real)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  SELECT dc.id, dc.document_id, dc.content,
    ts_rank(dc.fts, websearch_to_tsquery('english', search_query)) AS rank
  FROM document_chunks dc
  WHERE dc.user_id = match_user_id
    AND dc.fts @@ websearch_to_tsquery('english', search_query)
  ORDER BY rank DESC
  LIMIT match_count;
END;
$$;

-- Hybrid search RPC combining vector + FTS with RRF
CREATE OR REPLACE FUNCTION hybrid_search(
  query_embedding vector(768),
  search_query text,
  match_user_id uuid,
  match_count int DEFAULT 10,
  rrf_k int DEFAULT 60
)
RETURNS TABLE (id uuid, document_id uuid, content text, rrf_score real)
LANGUAGE plpgsql AS $$
BEGIN
  RETURN QUERY
  WITH vector_results AS (
    SELECT dc.id, dc.document_id, dc.content,
      ROW_NUMBER() OVER (ORDER BY dc.embedding <=> query_embedding) as rank
    FROM document_chunks dc
    WHERE dc.user_id = match_user_id
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count * 2
  ),
  fts_results AS (
    SELECT dc.id, dc.document_id, dc.content,
      ROW_NUMBER() OVER (ORDER BY ts_rank(dc.fts, websearch_to_tsquery('english', search_query)) DESC) as rank
    FROM document_chunks dc
    WHERE dc.user_id = match_user_id
      AND dc.fts @@ websearch_to_tsquery('english', search_query)
    ORDER BY ts_rank(dc.fts, websearch_to_tsquery('english', search_query)) DESC
    LIMIT match_count * 2
  ),
  combined AS (
    SELECT COALESCE(v.id, f.id) as id,
      COALESCE(v.document_id, f.document_id) as document_id,
      COALESCE(v.content, f.content) as content,
      COALESCE(1.0 / (rrf_k + v.rank), 0)::real + COALESCE(1.0 / (rrf_k + f.rank), 0)::real as score
    FROM vector_results v
    FULL OUTER JOIN fts_results f ON v.id = f.id
  )
  SELECT combined.id, combined.document_id, combined.content, combined.score as rrf_score
  FROM combined
  ORDER BY combined.score DESC
  LIMIT match_count;
END;
$$;
