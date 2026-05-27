-- Schema info view for SQL agent awareness
CREATE OR REPLACE VIEW public.table_schema_info AS
SELECT
  table_name,
  column_name,
  data_type,
  is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('ie_sales', 'ie_employees')
ORDER BY table_name, ordinal_position;

-- Read-only SQL execution function for the SQL agent
CREATE OR REPLACE FUNCTION exec_readonly_sql(query_text text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  result jsonb;
BEGIN
  -- Only allow SELECT
  IF upper(ltrim(query_text)) NOT LIKE 'SELECT%' THEN
    RAISE EXCEPTION 'Only SELECT queries are allowed';
  END IF;

  EXECUTE format('SELECT jsonb_agg(row_to_json(t)) FROM (%s) t', query_text) INTO result;
  RETURN COALESCE(result, '[]'::jsonb);
END;
$$;
