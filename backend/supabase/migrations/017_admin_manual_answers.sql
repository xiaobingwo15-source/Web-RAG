-- Admin Manual Answer Feature
-- Extends messages table to support admin responses and auto-flagging of AI refusal messages

-- 1. Extend the role constraint to include 'admin'
ALTER TABLE public.messages
  DROP CONSTRAINT IF EXISTS messages_role_check;

ALTER TABLE public.messages
  ADD CONSTRAINT messages_role_check
  CHECK (role IN ('user', 'assistant', 'admin'));

-- 2. Add needs_attention flag
ALTER TABLE public.messages
  ADD COLUMN IF NOT EXISTS needs_attention boolean NOT NULL DEFAULT false;

-- 3. Index for efficiently querying flagged messages
CREATE INDEX IF NOT EXISTS idx_messages_needs_attention
  ON public.messages(needs_attention)
  WHERE needs_attention = true;

-- 4. Trigger function: auto-flag known refusal patterns on INSERT
CREATE OR REPLACE FUNCTION public.flag_refusal_messages()
RETURNS trigger AS $$
BEGIN
  IF NEW.role = 'assistant' AND (
    NEW.content ILIKE '%couldn''t find relevant information%'
    OR NEW.content ILIKE '%AI service is temporarily unavailable%'
  ) THEN
    NEW.needs_attention := true;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 5. Attach trigger to messages table
DROP TRIGGER IF EXISTS trg_flag_refusal_messages ON public.messages;
CREATE TRIGGER trg_flag_refusal_messages
  BEFORE INSERT ON public.messages
  FOR EACH ROW
  EXECUTE FUNCTION public.flag_refusal_messages();

-- 6. Enable Realtime on messages table
ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;
