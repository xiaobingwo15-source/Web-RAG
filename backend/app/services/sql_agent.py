import asyncio
import logging
from openai import AsyncOpenAI, APIError, RateLimitError
from langfuse import observe
from app.services.gemini import MAX_RETRIES, BACKOFF_BASE, _is_retryable, _models_to_try

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
async def generate_sql(client: AsyncOpenAI, question: str, schema: str) -> str:
    prompt = f"Schema:\n{schema}\n\nQuestion: {question}"

    last_error = None
    for model_name in _models_to_try():
        for attempt in range(MAX_RETRIES):
            try:
                response = await client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": SQL_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=512,
                )

                sql = response.choices[0].message.content.strip()
                sql = sql.strip("```sql").strip("```").strip()
                return sql

            except RateLimitError as e:
                last_error = e
                logger.warning(f"generate_sql rate limited (429) on {model_name}, switching to next model")
                break
            except APIError as e:
                last_error = e
                if not _is_retryable(e):
                    raise
                delay = BACKOFF_BASE * (2 ** attempt)
                logger.warning(f"generate_sql attempt {attempt + 1} failed: {getattr(e, 'status_code', '?')}, retrying in {delay:.0f}s")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)

    raise last_error
