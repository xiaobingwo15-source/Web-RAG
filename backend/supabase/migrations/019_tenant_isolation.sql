-- Migration 019: Tenant-isolated RAG backend.
-- Moves from one global admin/shared knowledge base to one admin per website tenant.

CREATE TABLE IF NOT EXISTS public.tenants (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  slug text NOT NULL UNIQUE,
  allowed_origins text[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS public.tenant_admin_invites (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
  email text NOT NULL,
  token_hash text NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.tenant_admin_invites ENABLE ROW LEVEL SECURITY;

INSERT INTO public.tenants (id, name, slug, allowed_origins, status)
VALUES ('00000000-0000-0000-0000-000000000001', 'Default Tenant', 'default', ARRAY['http://localhost:5173'], 'active')
ON CONFLICT (id) DO NOTHING;

ALTER TABLE public.profiles ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.file_search_stores ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.documents ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.document_chunks ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.threads ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.agent_traces ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);
ALTER TABLE public.system_settings ADD COLUMN IF NOT EXISTS tenant_id uuid REFERENCES public.tenants(id);

ALTER TABLE public.threads ADD COLUMN IF NOT EXISTS client_session_id text;
ALTER TABLE public.messages ADD COLUMN IF NOT EXISTS client_session_id text;
ALTER TABLE public.threads ALTER COLUMN user_id DROP NOT NULL;
ALTER TABLE public.messages ALTER COLUMN user_id DROP NOT NULL;

UPDATE public.profiles SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.file_search_stores SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.documents SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.document_chunks SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.threads SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.messages SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.agent_traces SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;
UPDATE public.system_settings SET tenant_id = '00000000-0000-0000-0000-000000000001' WHERE tenant_id IS NULL;

ALTER TABLE public.file_search_stores ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.documents ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.document_chunks ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.threads ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.messages ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.agent_traces ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE public.system_settings ALTER COLUMN tenant_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_one_admin_per_tenant
  ON public.profiles(tenant_id)
  WHERE role = 'admin';

CREATE INDEX IF NOT EXISTS idx_profiles_tenant ON public.profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_threads_tenant ON public.threads(tenant_id);
CREATE INDEX IF NOT EXISTS idx_messages_tenant ON public.messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_documents_tenant ON public.documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_tenant ON public.document_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_agent_traces_tenant ON public.agent_traces(tenant_id);
CREATE INDEX IF NOT EXISTS idx_file_search_stores_tenant ON public.file_search_stores(tenant_id);

ALTER TABLE public.system_settings DROP CONSTRAINT IF EXISTS system_settings_pkey;
ALTER TABLE public.system_settings ADD CONSTRAINT system_settings_pkey PRIMARY KEY (tenant_id, key);

CREATE OR REPLACE FUNCTION public.current_tenant_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT tenant_id FROM public.profiles WHERE id = auth.uid()
$$;

CREATE OR REPLACE FUNCTION public.is_tenant_admin(check_tenant_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM public.profiles
    WHERE id = auth.uid()
      AND role = 'admin'
      AND tenant_id = check_tenant_id
  )
$$;

CREATE OR REPLACE FUNCTION public.is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.profiles WHERE id = auth.uid() AND role = 'admin'
  )
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email, role, tenant_id)
  VALUES (new.id, new.email, 'client', NULL);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER SET search_path = public;

DROP POLICY IF EXISTS "Authenticated users can read profiles" ON public.profiles;
DROP POLICY IF EXISTS "Admin can view all profiles" ON public.profiles;
DROP POLICY IF EXISTS "Tenant admin can view profiles" ON public.profiles;
CREATE POLICY "Tenant admin can view profiles"
  ON public.profiles FOR SELECT
  USING (id = auth.uid() OR public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Admin can view all threads" ON public.threads;
DROP POLICY IF EXISTS "Users can view own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can insert own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can update own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can delete own threads" ON public.threads;
DROP POLICY IF EXISTS "Tenant admin can view threads" ON public.threads;
DROP POLICY IF EXISTS "Users can view tenant own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can insert tenant own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can update tenant own threads" ON public.threads;
DROP POLICY IF EXISTS "Users can delete tenant own threads" ON public.threads;
CREATE POLICY "Users can view tenant own threads"
  ON public.threads FOR SELECT
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can insert tenant own threads"
  ON public.threads FOR INSERT
  WITH CHECK (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can update tenant own threads"
  ON public.threads FOR UPDATE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id())
  WITH CHECK (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can delete tenant own threads"
  ON public.threads FOR DELETE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Tenant admin can view threads"
  ON public.threads FOR SELECT
  USING (public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Admin can view all messages" ON public.messages;
DROP POLICY IF EXISTS "Users can view own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can insert own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can update own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can delete own messages" ON public.messages;
DROP POLICY IF EXISTS "Tenant admin can view messages" ON public.messages;
DROP POLICY IF EXISTS "Users can view tenant own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can insert tenant own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can update tenant own messages" ON public.messages;
DROP POLICY IF EXISTS "Users can delete tenant own messages" ON public.messages;
CREATE POLICY "Users can view tenant own messages"
  ON public.messages FOR SELECT
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can insert tenant own messages"
  ON public.messages FOR INSERT
  WITH CHECK (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can update tenant own messages"
  ON public.messages FOR UPDATE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id())
  WITH CHECK (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Users can delete tenant own messages"
  ON public.messages FOR DELETE
  USING (user_id = auth.uid() AND tenant_id = public.current_tenant_id());
CREATE POLICY "Tenant admin can view messages"
  ON public.messages FOR SELECT
  USING (public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Users manage own store" ON public.file_search_stores;
DROP POLICY IF EXISTS "Tenant admin manage own store" ON public.file_search_stores;
CREATE POLICY "Tenant admin manage own store" ON public.file_search_stores
  FOR ALL
  USING (auth.uid() = user_id AND public.is_tenant_admin(tenant_id))
  WITH CHECK (auth.uid() = user_id AND public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Users manage own traces" ON public.agent_traces;
DROP POLICY IF EXISTS "Users manage tenant own traces" ON public.agent_traces;
CREATE POLICY "Users manage tenant own traces" ON public.agent_traces
  FOR ALL
  USING (auth.uid() = user_id AND tenant_id = public.current_tenant_id())
  WITH CHECK (auth.uid() = user_id AND tenant_id = public.current_tenant_id());

DROP POLICY IF EXISTS "Select documents policy" ON public.documents;
DROP POLICY IF EXISTS "Modify own documents policy" ON public.documents;
CREATE POLICY "Tenant document read policy" ON public.documents FOR SELECT
  USING (auth.uid() = user_id OR tenant_id = public.current_tenant_id());
CREATE POLICY "Tenant admin document write policy" ON public.documents FOR ALL
  USING (auth.uid() = user_id AND public.is_tenant_admin(tenant_id))
  WITH CHECK (auth.uid() = user_id AND public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Select chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Insert chunks policy" ON public.document_chunks;
DROP POLICY IF EXISTS "Delete chunks policy" ON public.document_chunks;
CREATE POLICY "Tenant chunk read policy" ON public.document_chunks FOR SELECT
  USING (auth.uid() = user_id OR tenant_id = public.current_tenant_id());
CREATE POLICY "Tenant admin chunk insert policy" ON public.document_chunks FOR INSERT
  WITH CHECK (auth.uid() = user_id AND public.is_tenant_admin(tenant_id));
CREATE POLICY "Tenant admin chunk delete policy" ON public.document_chunks FOR DELETE
  USING (auth.uid() = user_id AND public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Admin manage system_settings" ON public.system_settings;
CREATE POLICY "Tenant admin manage system_settings"
  ON public.system_settings FOR ALL
  USING (public.is_tenant_admin(tenant_id))
  WITH CHECK (public.is_tenant_admin(tenant_id));

DROP POLICY IF EXISTS "Tenant admin read own tenant" ON public.tenants;
CREATE POLICY "Tenant admin read own tenant"
  ON public.tenants FOR SELECT
  USING (public.is_tenant_admin(id));

CREATE OR REPLACE FUNCTION search_chunks_fts(
  search_query text,
  match_user_id uuid DEFAULT NULL,
  match_count int DEFAULT 10,
  match_tenant_id uuid DEFAULT NULL
)
RETURNS TABLE (id uuid, document_id uuid, content text, rank real)
LANGUAGE sql
STABLE
AS $$
  SELECT dc.id, dc.document_id, dc.content,
         ts_rank(dc.fts, plainto_tsquery('english', search_query)) AS rank
  FROM public.document_chunks dc
  WHERE dc.fts @@ plainto_tsquery('english', search_query)
    AND (
      (match_tenant_id IS NOT NULL AND dc.tenant_id = match_tenant_id)
      OR (match_tenant_id IS NULL AND match_user_id IS NOT NULL AND dc.user_id = match_user_id)
    )
  ORDER BY rank DESC
  LIMIT match_count;
$$;
