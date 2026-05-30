-- Migration 021: Tenant Slug Signup + Admin Approval
-- Adds status column to profiles, updates trigger to read tenant_slug from metadata,
-- blocks pending/suspended users from writing via RLS.

-- 1. Add status column (existing users default to 'approved')
ALTER TABLE public.profiles
ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'approved'
CHECK (status IN ('pending', 'approved', 'suspended'));

-- 2. Index for admin queries
CREATE INDEX IF NOT EXISTS idx_profiles_status ON public.profiles(status);

-- 3. Update trigger: read tenant_slug from user metadata, set status='pending'
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
DECLARE
  target_tenant_id uuid;
  tenant_slug text;
BEGIN
  tenant_slug := NEW.raw_user_meta_data->>'tenant_slug';

  IF tenant_slug IS NOT NULL AND tenant_slug != '' THEN
    SELECT id INTO target_tenant_id
    FROM public.tenants
    WHERE slug = tenant_slug AND status = 'active';
  END IF;

  INSERT INTO public.profiles (id, email, role, tenant_id, status)
  VALUES (NEW.id, NEW.email, 'client', target_tenant_id, 'pending');

  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

-- 4. Helper function: is current user approved?
CREATE OR REPLACE FUNCTION public.is_approved_user()
RETURNS boolean
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles
    WHERE id = auth.uid() AND status = 'approved'
  )
$$;

-- 5. Update RLS on threads — require approval for writes
DROP POLICY IF EXISTS "Users can insert tenant own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can update tenant own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can delete tenant own threads" ON public.threads;

CREATE POLICY "Users can insert tenant own threads"
  ON public.threads FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );

CREATE POLICY "Users can update tenant own threads"
  ON public.threads FOR UPDATE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id())
  WITH CHECK (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );

CREATE POLICY "Users can delete tenant own threads"
  ON public.threads FOR DELETE
  USING (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );

-- 6. Update RLS on messages — require approval for writes
DROP POLICY IF EXISTS "Users can insert tenant own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can update tenant own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can delete tenant own messages" ON public.messages;

CREATE POLICY "Users can insert tenant own messages"
  ON public.messages FOR INSERT
  WITH CHECK (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );

CREATE POLICY "Users can update tenant own messages"
  ON public.messages FOR UPDATE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id())
  WITH CHECK (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );

CREATE POLICY "Users can delete tenant own messages"
  ON public.messages FOR DELETE
  USING (
    user_id = auth.uid()
    AND tenant_id = public.current_tenant_id()
    AND public.is_approved_user()
  );
