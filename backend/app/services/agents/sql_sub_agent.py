import logging
from collections.abc import AsyncGenerator
from app.services.gemini import get_gemini_client, generate_chat_response_stream
from app.services.sql_agent import generate_sql
from app.services.sql_engine import get_schema_description, execute_readonly_sql

logger = logging.getLogger(__name__)


async def execute(
    message: str,
    history: list,
) -> AsyncGenerator[dict, None]:
    yield {"type": "thought", "content": "Analyzing question for SQL query generation..."}

    client = get_gemini_client()
    schema = get_schema_description()

    yield {"type": "thought", "content": "Generating SQL query..."}
    sql = await generate_sql(client, message, schema)
    yield {"type": "thought", "content": f"Generated SQL: {sql}"}

    yield {"type": "thought", "content": "Executing query..."}
    try:
        result = execute_readonly_sql(sql)
        yield {"type": "thought", "content": f"Query returned {len(result['rows'])} rows."}
    except Exception as e:
        yield {"type": "thought", "content": f"SQL execution failed: {e}"}
        yield {"type": "token", "content": f"I encountered an error querying the database: {e}"}
        return

    result_text = f"SQL Query: {sql}\n\nResults ({len(result['rows'])} rows):\n"
    for row in result["rows"][:20]:
        result_text += str(row) + "\n"

    yield {"type": "thought", "content": "Summarizing results..."}
    summary_prompt = f"Based on the following database query results, answer the user's question.\n\nQuestion: {message}\n\n{result_text}"

    async for chunk in generate_chat_response_stream(client, summary_prompt, history):
        yield {"type": "token", "content": chunk}
