-- Drop the FK constraint on retrieval_logs.user_id
-- The column references auth.users(id) but anonymous/widget users may not
-- have a persistent row in auth.users, causing FK violations on insert.
-- The column remains uuid and nullable (ON DELETE SET NULL intent is preserved).
ALTER TABLE retrieval_logs DROP CONSTRAINT IF EXISTS retrieval_logs_user_id_fkey;
