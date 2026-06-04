-- Enable anonymous widget/landing-page feedback in the RAG quality loop.
-- 1. Add client_session_id column to identify widget sessions
-- 2. Drop user_id FK (same pattern as migration 029 on retrieval_logs)
-- 3. Replace monolithic unique constraint with partial unique indexes

ALTER TABLE message_feedback ADD COLUMN IF NOT EXISTS client_session_id text;

ALTER TABLE message_feedback DROP CONSTRAINT IF EXISTS message_feedback_user_id_fkey;

ALTER TABLE message_feedback DROP CONSTRAINT IF EXISTS message_feedback_user_id_thread_id_message_id_key;

-- Auth feedback: unique per user per message (when user_id is set)
CREATE UNIQUE INDEX IF NOT EXISTS idx_mf_user_dedup
  ON message_feedback(user_id, thread_id, message_id)
  WHERE user_id IS NOT NULL;

-- Widget feedback: unique per session per message (when client_session_id is set)
CREATE UNIQUE INDEX IF NOT EXISTS idx_mf_session_dedup
  ON message_feedback(client_session_id, thread_id, message_id)
  WHERE client_session_id IS NOT NULL;
