-- Migration 012: Grant SELECT on auth.users to authenticated role
-- Required because threads.user_id has a FK to auth.users, and PostgREST
-- needs to resolve this relationship when querying threads as an authenticated user.
GRANT SELECT ON auth.users TO authenticated;
