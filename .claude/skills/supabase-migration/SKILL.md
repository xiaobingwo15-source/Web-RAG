---
name: supabase-migration
description: Create and apply Supabase SQL migrations via MCP. Use when modifying database schema, RLS policies, triggers, or functions.
argument-hint: "[description-of-migration]"
allowed-tools: mcp__supabase__execute_sql mcp__supabase__list_tables mcp__supabase__get_advisors Read Write Edit Glob
---

# Supabase Migration Skill

You are writing a database migration for a Supabase-backed RAG application. Follow this workflow.

## Step 1: Understand Current State

Before writing SQL, check what exists:

```sql
-- List tables
SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';

-- Check specific table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns WHERE table_name = 'your_table' AND table_schema = 'public';

-- Check existing RLS policies
SELECT schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
FROM pg_policies WHERE schemaname = 'public';

-- Check existing functions
SELECT routine_name, routine_type FROM information_schema.routines WHERE routine_schema = 'public';
```

Use `mcp__supabase__list_tables` with `verbose: true` for a quick overview.

## Step 2: Write the Migration

Save to `backend/supabase/migrations/NNN_description.sql` where NNN is the next sequence number.

**Migration template:**
```sql
-- Migration: NNN - Description
-- What: Brief explanation
-- Why: Business reason

-- 1. Schema changes (CREATE TABLE, ALTER TABLE, ADD COLUMN)
-- 2. Functions (CREATE OR REPLACE FUNCTION)
-- 3. Triggers (CREATE OR REPLACE TRIGGER)
-- 4. RLS policies (ALTER TABLE ENABLE ROW LEVEL SECURITY, CREATE POLICY)
-- 5. Indexes
-- 6. Data fixes (UPDATE/INSERT for existing rows)
```

**Rules:**
- Always use `CREATE OR REPLACE` for functions (idempotent)
- Always use `IF NOT EXISTS` / `IF EXISTS` for tables and columns
- Never hardcode UUIDs — use subqueries or variables
- Order matters: create tables before policies that reference them
- For RLS: test both WITH CHECK (INSERT/UPDATE) and USING (SELECT/DELETE)

## Step 3: Apply via Supabase MCP

Apply using `mcp__supabase__apply_migration`:
```
name: "NNN_description"
query: <full SQL content>
```

## Step 4: Verify

After applying, run verification queries:

```sql
-- Verify table exists
SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'your_table');

-- Verify column exists
SELECT EXISTS (
  SELECT FROM information_schema.columns
  WHERE table_name = 'your_table' AND column_name = 'your_column'
);

-- Verify function exists
SELECT EXISTS (
  SELECT FROM information_schema.routines
  WHERE routine_name = 'your_function' AND routine_schema = 'public'
);

-- Verify RLS is enabled
SELECT relname, relrowsecurity FROM pg_class WHERE relname = 'your_table';

-- Check for security advisories
```

Use `mcp__supabase__get_advisors("security")` to catch missing RLS policies.

## Step 5: Check for Dependent Code

After migration, grep the codebase for references to changed tables/columns:
- `backend/app/services/database.py` — query functions
- `backend/app/routers/*.py` — API endpoints
- `frontend/src/lib/api.ts` — TypeScript interfaces

Update application code if column names or types changed.

## Common Patterns

### Adding a column with default
```sql
ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'approved';
```

### Safe trigger replacement
```sql
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  -- Always use NEW record, never query auth.users
  INSERT INTO public.profiles (id, email, role, tenant_id)
  VALUES (NEW.id, NEW.email, 'client', NULL);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
```

### RLS policy with helper function
```sql
CREATE OR REPLACE FUNCTION public.is_approved_user()
RETURNS boolean AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND status = 'approved'
  );
$$ LANGUAGE sql SECURITY DEFINER STABLE SET search_path = public;

CREATE POLICY "approved_users_only" ON public.threads
  FOR ALL USING (public.is_approved_user())
  WITH CHECK (public.is_approved_user());
```

## Pitfalls

| Pitfall | Fix |
|---------|-----|
| `NULL = NULL` evaluates to `NULL` in SQL, not `true` | Use `IS NOT DISTINCT FROM` or coalesce to defaults |
| RLS blocks the function that's supposed to fix it | Use `SECURITY DEFINER` on functions that need to bypass RLS |
| Trigger fires before profile exists | Use `AFTER INSERT` or ensure trigger doesn't query the same table |
| Migration order matters | Run schema changes before policies that reference them |
