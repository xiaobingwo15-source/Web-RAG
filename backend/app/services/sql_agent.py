import asyncio
import logging
from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError
from langfuse import observe
from app.services.gemini import PRIMARY_MODEL, MAX_RETRIES, BACKOFF_BASE, _is_retryable, _extract_retry_delay

logger = logging.getLogger(__name__)

SQL_PROMPT = (
    "You are a SQL query generator. Given a database schema and a natural language question, "
    "generate a valid PostgreSQL SELECT query that answers the question.\n\n"
    "Rules:\n"
    "- Only output the SQL query, nothing else\n"
    "- Only use SELECT statements\n"
    "- Use the exact table and column names from the schema\n"
    "- Use appropriate aggregations, GROUP BY, ORDER BY as needed\n"
    "- Do not use semicolons at the end"
)


@observe(name="generate_sql", as_type="generation")
async def generate_sql(client: genai.Client, question: str, schema: str) -> str:
    prompt = f"Schema:\n{schema}\n\nQuestion: {question}"

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.aio.models.generate_content(
                model=PRIMARY_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.1,
                    max_output_tokens=512,
                    system_instruction=SQL_PROMPT,
                ),
            )

            sql = response.candidates[0].content.parts[0].text.strip()
            sql = sql.strip("```sql").strip("```").strip()
            return sql

        except ServerError as e:
            last_error = e
            if not _is_retryable(e):
                raise
            delay = _extract_retry_delay(e) if e.code == 429 else BACKOFF_BASE * (2 ** attempt)
            logger.warning(f"generate_sql attempt {attempt + 1} failed: {e.code} {e.status}, retrying in {delay:.0f}s")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(delay)
        except ClientError:
            raise

    raise last_error
