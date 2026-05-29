-- Update refusal message trigger to match new professional response patterns
CREATE OR REPLACE FUNCTION public.flag_refusal_messages()
RETURNS trigger AS $$
BEGIN
  IF NEW.role = 'assistant' AND (
    NEW.content ILIKE '%don''t have the specific details%'
    OR NEW.content ILIKE '%wasn''t able to find reliable information%'
    OR NEW.content ILIKE '%AI service is temporarily unavailable%'
  ) THEN
    NEW.needs_attention := true;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
