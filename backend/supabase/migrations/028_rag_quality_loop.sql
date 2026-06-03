-- Migration 028: RAG quality loop evidence for admin review.
-- Additive only: preserves existing retrieval_logs and feedback records.

ALTER TABLE public.retrieval_logs
  ADD COLUMN IF NOT EXISTS sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS chunks jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS answer_message_id uuid REFERENCES public.messages(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS groundedness_score numeric,
  ADD COLUMN IF NOT EXISTS groundedness_flag boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS retrieval_quality text;

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_answer_message
  ON public.retrieval_logs(tenant_id, answer_message_id, created_at DESC)
  WHERE answer_message_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_groundedness_flag
  ON public.retrieval_logs(tenant_id, created_at DESC)
  WHERE groundedness_flag = true;

CREATE INDEX IF NOT EXISTS idx_message_feedback_rating_created
  ON public.message_feedback(tenant_id, rating, created_at DESC);
