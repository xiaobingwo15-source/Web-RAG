-- Fix: profiles with NULL tenant_id break RLS policies
-- The INSERT policy on threads/messages requires tenant_id = current_tenant_id(),
-- but current_tenant_id() returns NULL when profiles.tenant_id is NULL.
-- NULL = NULL evaluates to NULL (not true), so all inserts fail with RLS violation.

-- 1. Assign existing profiles with NULL tenant_id to the first active tenant
UPDATE public.profiles
SET tenant_id = (SELECT id FROM public.tenants WHERE status = 'active' LIMIT 1)
WHERE tenant_id IS NULL;

-- 2. Fix the trigger so future signups get auto-assigned to a default tenant
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
DECLARE
  default_tenant_id uuid;
BEGIN
  SELECT id INTO default_tenant_id FROM public.tenants WHERE status = 'active' LIMIT 1;

  INSERT INTO public.profiles (id, email, role, tenant_id)
  VALUES (new.id, new.email, 'client', default_tenant_id);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;
