-- 031_upload_sessions.sql
-- Tracks chunked file uploads for resilient admin upload (survives page refresh)

CREATE TABLE public.upload_sessions (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  tenant_id       uuid REFERENCES public.tenants(id),
  filename        text NOT NULL,
  mime_type       text NOT NULL,
  total_size      bigint NOT NULL,
  chunk_size      int NOT NULL,
  total_chunks    int NOT NULL,
  uploaded_chunks int NOT NULL DEFAULT 0,
  status          text NOT NULL DEFAULT 'uploading'
                  CHECK (status IN ('uploading', 'completing', 'completed', 'failed', 'expired')),
  use_ocr         boolean NOT NULL DEFAULT false,
  pdf_parser_mode text NOT NULL DEFAULT 'auto',
  document_id     uuid REFERENCES public.documents(id),
  error_message   text,
  created_at      timestamptz NOT NULL DEFAULT now(),
  updated_at      timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.upload_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own upload sessions" ON public.upload_sessions
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE INDEX idx_upload_sessions_user ON public.upload_sessions(user_id);
CREATE INDEX idx_upload_sessions_status ON public.upload_sessions(status);
