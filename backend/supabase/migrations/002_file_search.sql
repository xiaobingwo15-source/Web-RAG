-- Table: file_search_stores (one per user, holds Gemini store resource name)
CREATE TABLE public.file_search_stores (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
  store_name text NOT NULL,
  display_name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.file_search_stores ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own store" ON public.file_search_stores
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_file_search_stores_user ON public.file_search_stores(user_id);

-- Table: documents (one per uploaded file)
CREATE TABLE public.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  store_id uuid NOT NULL REFERENCES public.file_search_stores(id) ON DELETE CASCADE,
  filename text NOT NULL,
  mime_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processed', 'failed')),
  operation_name text,
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own documents" ON public.documents
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_documents_user ON public.documents(user_id);
CREATE INDEX idx_documents_store ON public.documents(store_id);
CREATE INDEX idx_documents_status ON public.documents(status);
