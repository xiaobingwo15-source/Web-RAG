-- Commercial database hardening aligned to Orion's database rules.

CREATE TABLE IF NOT EXISTS public.operation_audit_logs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES public.tenants(id) ON DELETE SET NULL,
  actor_user_id uuid,
  actor_email text,
  actor_role text,
  action text NOT NULL,
  resource_type text NOT NULL,
  resource_id text,
  before_snapshot jsonb,
  after_snapshot jsonb,
  ip_address text,
  user_agent text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS operation_audit_logs_tenant_created_idx
  ON public.operation_audit_logs(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS operation_audit_logs_resource_idx
  ON public.operation_audit_logs(resource_type, resource_id);

ALTER TABLE public.operation_audit_logs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS operation_audit_logs_admin_select ON public.operation_audit_logs;
CREATE POLICY operation_audit_logs_admin_select
  ON public.operation_audit_logs
  FOR SELECT
  TO authenticated
  USING (
    tenant_id IN (
      SELECT tenant_id
      FROM public.profiles
      WHERE id = auth.uid()
        AND role = 'admin'
        AND status = 'approved'
    )
  );

DROP POLICY IF EXISTS operation_audit_logs_service_role_all ON public.operation_audit_logs;
CREATE POLICY operation_audit_logs_service_role_all
  ON public.operation_audit_logs
  FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);

ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS attention_status text NOT NULL DEFAULT 'none'
  CHECK (attention_status IN ('none', 'needs_admin', 'responded', 'dismissed'));

UPDATE public.messages
SET attention_status = CASE WHEN needs_attention THEN 'needs_admin' ELSE 'none' END
WHERE attention_status = 'none';

CREATE INDEX IF NOT EXISTS messages_attention_status_idx
  ON public.messages(tenant_id, attention_status, created_at DESC);

CREATE OR REPLACE FUNCTION public.flag_refusal_messages()
RETURNS trigger AS $$
BEGIN
  IF NEW.role = 'assistant' AND (
    NEW.content ILIKE '%don''t have the specific details%'
    OR NEW.content ILIKE '%wasn''t able to find reliable information%'
    OR NEW.content ILIKE '%AI service is temporarily unavailable%'
  ) THEN
    NEW.needs_attention := true;
    NEW.attention_status := 'needs_admin';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

ALTER TABLE public.retrieval_logs
  ADD COLUMN IF NOT EXISTS grounding_status text NOT NULL DEFAULT 'not_checked'
  CHECK (grounding_status IN ('not_checked', 'ok', 'low_confidence', 'ungrounded'));

UPDATE public.retrieval_logs
SET grounding_status = CASE
  WHEN groundedness_flag THEN 'ungrounded'
  WHEN groundedness_score IS NULL THEN 'not_checked'
  WHEN groundedness_score < 0.7 THEN 'low_confidence'
  ELSE 'ok'
END
WHERE grounding_status = 'not_checked';

CREATE INDEX IF NOT EXISTS retrieval_logs_grounding_status_idx
  ON public.retrieval_logs(tenant_id, grounding_status, created_at DESC);

ALTER TABLE public.rag_eval_results
  ADD COLUMN IF NOT EXISTS result_status text NOT NULL DEFAULT 'failed'
  CHECK (result_status IN ('passed', 'failed', 'warning', 'skipped'));

UPDATE public.rag_eval_results
SET result_status = CASE WHEN passed THEN 'passed' ELSE 'failed' END
WHERE result_status = 'failed';

CREATE INDEX IF NOT EXISTS rag_eval_results_result_status_idx
  ON public.rag_eval_results(tenant_id, result_status, created_at DESC);

CREATE OR REPLACE FUNCTION public.exec_readonly_sql(query_text text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  result jsonb;
  table_ref text;
  normalized_ref text;
BEGIN
  IF query_text IS NULL OR btrim(query_text) = '' THEN
    RAISE EXCEPTION 'Query is required';
  END IF;

  IF btrim(query_text) ~ ';|--|/\*|\*/' THEN
    RAISE EXCEPTION 'Only a single SELECT statement is allowed';
  END IF;

  IF upper(ltrim(query_text)) !~ '^SELECT\M' THEN
    RAISE EXCEPTION 'Only SELECT queries are allowed';
  END IF;

  IF query_text ~* '\m(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|CALL|COPY)\M' THEN
    RAISE EXCEPTION 'Query contains blocked keywords';
  END IF;

  FOR table_ref IN
    SELECT (regexp_matches(lower(query_text), '\m(?:from|join)\s+("?[\w\.]+"?)', 'g'))[1]
  LOOP
    normalized_ref := replace(replace(table_ref, '"', ''), 'public.', '');
    IF normalized_ref NOT IN ('ie_sales', 'ie_employees') THEN
      RAISE EXCEPTION 'Table % is not allowed', normalized_ref;
    END IF;
  END LOOP;

  IF lower(query_text) !~ '\m(from|join)\s+(public\.)?(ie_sales|ie_employees)\M' THEN
    RAISE EXCEPTION 'Query must reference an allowed table';
  END IF;

  EXECUTE format('SELECT jsonb_agg(row_to_json(t)) FROM (%s) t', query_text) INTO result;
  RETURN COALESCE(result, '[]'::jsonb);
END;
$$;
