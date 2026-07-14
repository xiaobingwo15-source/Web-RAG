-- Restore conflict targets that PostgREST can infer for feedback upserts.
-- NULL values remain distinct, so each constraint applies only to its actor type.

BEGIN;

ALTER TABLE public.message_feedback
  ADD CONSTRAINT message_feedback_user_dedup UNIQUE (user_id, thread_id, message_id);

ALTER TABLE public.message_feedback
  ADD CONSTRAINT message_feedback_session_dedup UNIQUE (client_session_id, thread_id, message_id);

DROP INDEX IF EXISTS public.idx_mf_user_dedup;
DROP INDEX IF EXISTS public.idx_mf_session_dedup;

COMMIT;
