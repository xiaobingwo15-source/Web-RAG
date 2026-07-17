-- Migration 038: Make assistant streaming state finite and recoverable.

-- Repair placeholders abandoned by older deployments without deleting chat data.
UPDATE public.messages
SET
    status = 'failed',
    content = CASE
        WHEN btrim(content) = '' THEN 'This response was interrupted. Please try again.'
        ELSE content
    END
WHERE status = 'streaming'
  AND created_at < now() - interval '135 seconds';

-- Normalize unexpected legacy values before enforcing the public status contract.
UPDATE public.messages
SET status = 'complete'
WHERE status NOT IN ('streaming', 'complete', 'failed');

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'messages_status_valid'
          AND conrelid = 'public.messages'::regclass
    ) THEN
        ALTER TABLE public.messages
            ADD CONSTRAINT messages_status_valid
            CHECK (status IN ('streaming', 'complete', 'failed'));
    END IF;
END $$;
