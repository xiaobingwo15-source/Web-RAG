---
description: Supabase health check — schema verification, RLS audit, performance advisors, and data integrity
---

# Supabase Health Check

Verify Supabase database health, security policies, and data integrity. Report findings with evidence.

## Step 1: Schema Verification

List all tables and confirm expected schema exists:

```
mcp__supabase__list_tables(schemas=["public"], verbose=true)
```

Expected tables (from migrations):
- `profiles` — user profiles with role (admin/client)
- `documents` — uploaded document metadata
- `document_chunks` — text chunks for FTS
- `conversations` / `messages` — chat history
- `system_settings` — DB-backed config

Report any missing or unexpected tables.

## Step 2: Security Audit

Check for RLS and security advisories:

```
mcp__supabase__get_advisors(type="security")
```

Expected: No critical vulnerabilities. Report any advisories with their remediation URLs.

Common issues to watch for:
- Tables without RLS enabled
- Overly permissive policies (e.g., `SELECT` for anon role)
- Missing policies on sensitive tables

## Step 3: Performance Check

Check for performance advisories:

```
mcp__supabase__get_advisors(type="performance")
```

Report any missing indexes or slow query warnings.

## Step 4: Data Integrity

Run spot-check queries via `mcp__supabase__execute_sql`:

```sql
-- Check document statuses
SELECT status, count(*) FROM documents GROUP BY status;

-- Check chunk counts per document
SELECT d.id, d.title, count(c.id) as chunk_count
FROM documents d
LEFT JOIN document_chunks c ON c.document_id = d.id
GROUP BY d.id, d.title
ORDER BY chunk_count DESC
LIMIT 10;

-- Check profiles exist
SELECT role, count(*) FROM profiles GROUP BY role;
```

Report:
- Are documents in expected states (processed/pending/failed)?
- Do chunk counts look reasonable (not 0 for processed docs)?
- Are both admin and client profiles present?

## Step 5: Migration Status

List applied migrations:

```
mcp__supabase__list_migrations()
```

Compare against files in `backend/supabase/migrations/`. Report any drift.

## Step 6: Recent Logs (if issues found)

If any step shows problems, check logs:

```
mcp__supabase__get_logs(service="postgres")
```

Look for errors in the last 24 hours related to RLS violations, constraint failures, or connection issues.

## Report

| Check | Status | Details |
|-------|--------|---------|
| Schema | PASS/FAIL | Missing tables |
| Security | PASS/WARN/FAIL | Advisory count |
| Performance | PASS/WARN | Advisory count |
| Data integrity | PASS/WARN | Chunk counts, document states |
| Migrations | PASS/DRIFT | Applied vs expected |

If all PASS, Supabase is healthy. If any FAIL, investigate with the specific error details.
