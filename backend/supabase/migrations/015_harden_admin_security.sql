-- Migration 015: Harden admin-owned secrets and profile role management.

-- Clients must not read raw provider keys directly from Supabase.
DROP POLICY IF EXISTS "Authenticated users read system_settings" ON public.system_settings;

-- Clients must not be able to promote themselves by updating public.profiles.role.
DROP POLICY IF EXISTS "Users can update own profile" ON public.profiles;
