-- Migration 016: Allow authenticated users to read profiles role column
-- This is REQUIRED for the documents RLS subquery to work correctly.
-- Without this, a client user cannot evaluate:
--   (SELECT role FROM public.profiles WHERE id = user_id) = 'admin'
-- because the client's RLS on profiles blocks reading the admin's row,
-- causing the subquery to return NULL and the shared knowledge base to be invisible.

-- Allow any authenticated user to read all profiles (id, role needed for RLS subqueries)
CREATE POLICY "Authenticated users can read profiles"
    ON public.profiles FOR SELECT
    USING (auth.uid() IS NOT NULL);
