-- Migration 036: Add streaming status to messages
-- Allows the RAG pipeline to continue running in the background even when the
-- client disconnects.  A placeholder assistant message is created with
-- status='streaming' before the pipeline starts; when the pipeline finishes,
-- the content is written and status flips to 'complete'.

ALTER TABLE messages ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'complete';

-- Index for finding in-flight messages (e.g. for admin monitoring or cleanup)
CREATE INDEX IF NOT EXISTS idx_messages_status ON messages(status) WHERE status = 'streaming';
