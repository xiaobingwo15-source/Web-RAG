-- Migration 023: internal RAG evaluation storage.

CREATE TABLE IF NOT EXISTS public.rag_eval_suites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  name text NOT NULL DEFAULT 'Default RAG Eval Suite',
  description text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_eval_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  suite_id uuid REFERENCES public.rag_eval_suites(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  question text NOT NULL,
  expected_facts text[] NOT NULL DEFAULT '{}',
  expected_answer text,
  expected_document_id uuid,
  tags text[] NOT NULL DEFAULT '{}',
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_eval_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  suite_id uuid REFERENCES public.rag_eval_suites(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  retrieval_mode text NOT NULL DEFAULT 'hybrid'
    CHECK (retrieval_mode IN ('vector', 'fts', 'hybrid')),
  model_provider text,
  model_name text,
  total_cases integer NOT NULL DEFAULT 0,
  passed_cases integer NOT NULL DEFAULT 0,
  avg_context_relevance_score numeric NOT NULL DEFAULT 0,
  avg_groundedness_score numeric NOT NULL DEFAULT 0,
  avg_answer_relevance_score numeric NOT NULL DEFAULT 0,
  failure_reason text,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.rag_eval_results (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  run_id uuid NOT NULL REFERENCES public.rag_eval_runs(id) ON DELETE CASCADE,
  case_id uuid REFERENCES public.rag_eval_cases(id) ON DELETE SET NULL,
  question text NOT NULL,
  expected_facts text[] NOT NULL DEFAULT '{}',
  answer text NOT NULL DEFAULT '',
  sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  context_relevance_score numeric NOT NULL DEFAULT 0,
  groundedness_score numeric NOT NULL DEFAULT 0,
  answer_relevance_score numeric NOT NULL DEFAULT 0,
  passed boolean NOT NULL DEFAULT false,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.rag_eval_suites ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_eval_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_eval_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rag_eval_results ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Tenant admin manage rag eval suites"
  ON public.rag_eval_suites FOR ALL
  USING (public.is_tenant_admin(tenant_id))
  WITH CHECK (public.is_tenant_admin(tenant_id));

CREATE POLICY "Tenant admin manage rag eval cases"
  ON public.rag_eval_cases FOR ALL
  USING (public.is_tenant_admin(tenant_id))
  WITH CHECK (public.is_tenant_admin(tenant_id));

CREATE POLICY "Tenant admin manage rag eval runs"
  ON public.rag_eval_runs FOR ALL
  USING (public.is_tenant_admin(tenant_id))
  WITH CHECK (public.is_tenant_admin(tenant_id));

CREATE POLICY "Tenant admin manage rag eval results"
  ON public.rag_eval_results FOR ALL
  USING (public.is_tenant_admin(tenant_id))
  WITH CHECK (public.is_tenant_admin(tenant_id));

CREATE INDEX IF NOT EXISTS idx_rag_eval_suites_tenant
  ON public.rag_eval_suites(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_cases_tenant_enabled
  ON public.rag_eval_cases(tenant_id, enabled, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_runs_tenant_created
  ON public.rag_eval_runs(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_results_run
  ON public.rag_eval_results(tenant_id, run_id, created_at);
