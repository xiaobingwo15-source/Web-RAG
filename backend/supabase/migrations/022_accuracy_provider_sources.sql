-- Migration 022: provider settings, retrieval source support, and soft document archive.

ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS documents_status_check;

ALTER TABLE public.documents
  ADD CONSTRAINT documents_status_check
  CHECK (status IN ('pending', 'processed', 'failed', 'archived'));

ALTER TABLE public.threads
  ADD COLUMN IF NOT EXISTS archived_at timestamptz;

CREATE INDEX IF NOT EXISTS idx_documents_active_status
  ON public.documents(tenant_id, status)
  WHERE status <> 'archived';

CREATE INDEX IF NOT EXISTS idx_threads_unarchived
  ON public.threads(tenant_id, user_id, created_at DESC)
  WHERE archived_at IS NULL;

CREATE OR REPLACE FUNCTION search_chunks_fts(
  search_query text,
  match_user_id uuid DEFAULT NULL,
  match_count int DEFAULT 10,
  match_tenant_id uuid DEFAULT NULL
)
RETURNS TABLE (id uuid, document_id uuid, content text, rank real)
LANGUAGE sql
STABLE
AS $$
  SELECT dc.id, dc.document_id, dc.content,
         ts_rank(dc.fts, plainto_tsquery('english', search_query)) AS rank
  FROM public.document_chunks dc
  JOIN public.documents d ON d.id = dc.document_id
  WHERE d.status <> 'archived'
    AND dc.fts @@ plainto_tsquery('english', search_query)
    AND (
      (match_tenant_id IS NOT NULL AND dc.tenant_id = match_tenant_id)
      OR (match_tenant_id IS NULL AND match_user_id IS NOT NULL AND dc.user_id = match_user_id)
    )
  ORDER BY rank DESC
  LIMIT match_count;
$$;
