-- Add content hash for duplicate detection
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS content_hash text;
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON public.documents(user_id, content_hash);

-- Add sync status for lifecycle tracking
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS sync_status text
  DEFAULT 'synced' CHECK (sync_status IN ('synced', 'stale', 'reindexing'));

-- Add chunk count for dashboard visibility
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS chunk_count int DEFAULT 0;
