-- Promote RAG quality-loop evidence into reviewable draft eval cases.
ALTER TABLE public.rag_eval_cases
  ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'
    CHECK (status IN ('draft', 'active')),
  ADD COLUMN IF NOT EXISTS source_type text,
  ADD COLUMN IF NOT EXISTS source_ref_id text,
  ADD COLUMN IF NOT EXISTS retrieval_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

UPDATE public.rag_eval_cases
SET status = 'active'
WHERE status IS NULL;

CREATE INDEX IF NOT EXISTS idx_rag_eval_cases_tenant_status_created
  ON public.rag_eval_cases(tenant_id, status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_rag_eval_cases_quality_loop_source
  ON public.rag_eval_cases(tenant_id, source_type, source_ref_id)
  WHERE source_type IS NOT NULL AND source_ref_id IS NOT NULL;
