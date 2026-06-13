-- Additive diagnostics payload for RAG quality signal aggregation.
ALTER TABLE public.retrieval_logs
  ADD COLUMN IF NOT EXISTS diagnostics jsonb NOT NULL DEFAULT '{}'::jsonb;
