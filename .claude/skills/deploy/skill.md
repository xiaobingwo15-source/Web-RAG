---
name: deploy
description: Deploy frontend to Vercel and manage Supabase edge functions/migrations. Use when shipping changes to production.
---

# Deployment Workflow

## Frontend (Vercel)

The frontend auto-deploys from the `master` branch via Vercel. Production URL:
`https://frontend-five-gold-7n63puqbhf.vercel.app`

### Pre-deploy checklist
1. Run `cd frontend && npm run build` locally — must succeed with zero errors.
2. Check for hardcoded `localhost` URLs in `frontend/src/lib/api.ts` or env files.
3. Commit and push to `master`. Vercel deploys automatically.

### If deploy fails
- Check Vercel dashboard for build logs.
- Common: missing env vars in Vercel project settings (VITE_SUPABASE_URL, VITE_SUPABASE_ANON_KEY, VITE_API_URL).

## Backend (Supabase Edge Functions + Migrations)

### Migrations
- Use `mcp__supabase__apply_migration` for DDL changes.
- Use `mcp__supabase__execute_sql` for data queries.
- Always check `mcp__supabase__get_advisors` type="security" after schema changes.

### Edge Functions
- Use `mcp__supabase__deploy_edge_function` to deploy.
- List current functions with `mcp__supabase__list_edge_functions`.

### After any schema change
1. Run `mcp__supabase__get_advisors` type="security" — fix any RLS warnings.
2. Run `mcp__supabase__get_advisors` type="performance" — check for missing indexes.
3. Regenerate types: `mcp__supabase__generate_typescript_types`.

## Backend (FastAPI — self-hosted)

The Python backend runs on a separate server (not Supabase). After changes:
1. Restart the Uvicorn server.
2. Check `backend/.env` has all required keys.
3. Verify with `curl http://localhost:8000/health` or the production health endpoint.
