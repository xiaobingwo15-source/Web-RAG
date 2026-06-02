-- Migration 024: retrieval logs and message feedback for RAG learning.

-- Stores every retrieval request so admins can study what works and what doesn't.
CREATE TABLE IF NOT EXISTS public.retrieval_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  thread_id text,
  query text NOT NULL,
  retrieval_mode text NOT NULL DEFAULT 'hybrid'
    CHECK (retrieval_mode IN ('vector', 'fts', 'hybrid')),
  chunk_count integer NOT NULL DEFAULT 0,
  source_count integer NOT NULL DEFAULT 0,
  top_score numeric,
  duration_ms integer,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Simple thumbs-up / thumbs-down on assistant messages.
CREATE TABLE IF NOT EXISTS public.message_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  thread_id text NOT NULL,
  message_id text,
  rating smallint NOT NULL CHECK (rating IN (-1, 1)),
  comment text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (user_id, thread_id, message_id)
);

-- RLS
ALTER TABLE public.retrieval_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.message_feedback ENABLE ROW LEVEL SECURITY;

-- Tenant admins can read all logs for their tenant.
CREATE POLICY "Tenant admin read retrieval logs"
  ON public.retrieval_logs FOR SELECT
  USING (public.is_tenant_admin(tenant_id));

-- Service role inserts (backend uses service-role key, bypasses RLS).
CREATE POLICY "Service role insert retrieval logs"
  ON public.retrieval_logs FOR INSERT
  WITH CHECK (true);

-- Users can insert their own feedback.
CREATE POLICY "Users insert own feedback"
  ON public.message_feedback FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- Users can read their own feedback.
CREATE POLICY "Users read own feedback"
  ON public.message_feedback FOR SELECT
  USING (auth.uid() = user_id);

-- Tenant admins can read all feedback for their tenant.
CREATE POLICY "Tenant admin read feedback"
  ON public.message_feedback FOR SELECT
  USING (public.is_tenant_admin(tenant_id));

-- Indexes
CREATE INDEX IF NOT EXISTS idx_retrieval_logs_tenant_created
  ON public.retrieval_logs(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_retrieval_logs_zero_chunks
  ON public.retrieval_logs(tenant_id, created_at DESC)
  WHERE chunk_count = 0;

CREATE INDEX IF NOT EXISTS idx_message_feedback_thread
  ON public.message_feedback(tenant_id, thread_id, created_at);
