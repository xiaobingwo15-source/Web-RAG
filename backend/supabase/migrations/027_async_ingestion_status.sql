-- Async ingestion: add 'processing' status to documents table

ALTER TABLE public.documents
  DROP CONSTRAINT IF EXISTS documents_status_check;

ALTER TABLE public.documents
  ADD CONSTRAINT documents_status_check
  CHECK (status IN ('pending', 'processing', 'processed', 'failed', 'archived'));
