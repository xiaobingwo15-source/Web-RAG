-- RAGAS-style evaluation pipeline tables
-- Supports golden test sets and LLM-as-judge evaluation runs

CREATE TABLE IF NOT EXISTS public.eval_test_sets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
  document_id uuid REFERENCES public.documents(id) ON DELETE SET NULL,
  test_cases_json jsonb NOT NULL DEFAULT '[]',
  case_count int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_test_sets_tenant
  ON public.eval_test_sets(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.eval_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES public.tenants(id) ON DELETE CASCADE,
  test_set_id uuid REFERENCES public.eval_test_sets(id) ON DELETE SET NULL,
  total_cases int NOT NULL DEFAULT 0,
  metrics_json jsonb,
  results_json jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_tenant
  ON public.eval_runs(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_eval_runs_test_set
  ON public.eval_runs(test_set_id);

ALTER TABLE public.eval_test_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.eval_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY eval_test_sets_tenant_admin ON public.eval_test_sets
  FOR ALL USING (public.is_tenant_admin(tenant_id));

CREATE POLICY eval_runs_tenant_admin ON public.eval_runs
  FOR ALL USING (public.is_tenant_admin(tenant_id));
