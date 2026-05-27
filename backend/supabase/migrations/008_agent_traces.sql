-- Agent reasoning traces for debugging and UI display
CREATE TABLE IF NOT EXISTS public.agent_traces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  thread_id uuid REFERENCES public.threads(id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  agent_name text NOT NULL,
  thought text NOT NULL,
  tool_used text,
  tool_input text,
  tool_output text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.agent_traces ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users manage own traces" ON public.agent_traces
  FOR ALL USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_agent_traces_thread ON public.agent_traces(thread_id);
