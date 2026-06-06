import logging
from collections.abc import AsyncGenerator
from app.services.gemini import get_llm_client, generate_chat_response_stream
from app.services.sql_agent import generate_sql
from app.services.sql_engine import get_schema_description, execute_readonly_sql

logger = logging.getLogger(__name__)

SQL_SUMMARY_SYSTEM_PROMPT = (
    "You are a data analyst assistant. Summarize database query results "
    "in clear, natural language.\n\n"
    "Be conversational and direct. Highlight key numbers and trends. "
    "If the data is empty or inconclusive, say so honestly.\n\n"
    "Structure your answer:\n"
    "1. A brief direct answer (1-2 sentences)\n"
    "2. Key details and trends from the data\n"
    "3. A summary table if appropriate\n\n"
    "Use natural Markdown formatting. Include a brief data table if appropriate."
)


async def execute(
    message: str,
    history: list,
    images: list[str] | None = None,
) -> AsyncGenerator[dict, None]:
    yield {
        "type": "thought",
        "content": f"Preparing to query database for: \"{message[:80]}{'...' if len(message) > 80 else ''}\"",
        "action_type": "analyzing",
        "action_source": "sql",
        "action_data": {"question": message},
    }

    client = get_llm_client()
    schema = get_schema_description()

    yield {
        "type": "thought",
        "content": "Generating SQL from schema...",
        "action_type": "generating_sql",
        "action_source": "sql",
    }
    sql = await generate_sql(client, message, schema)
    yield {
        "type": "thought",
        "content": f"Generated SQL: {sql}",
        "action_type": "reading",
        "action_source": "sql",
        "action_data": {"sql": sql},
    }

    yield {
        "type": "thought",
        "content": "Executing query...",
        "action_type": "executing_sql",
        "action_source": "sql",
        "action_data": {"sql": sql},
    }
    try:
        result = execute_readonly_sql(sql)
        yield {
            "type": "thought",
            "content": f"Query returned {len(result['rows'])} rows.",
            "action_type": "reading",
            "action_source": "sql",
            "action_data": {
                "row_count": len(result["rows"]),
                "columns": result["columns"],
                "rows": result["rows"][:10],
                "sql": sql
            },
        }
    except Exception as e:
        logger.error(f"SQL execution failed: {e}", exc_info=True)
        yield {
            "type": "thought",
            "content": f"SQL execution failed: {e}",
            "action_type": "no_results",
            "action_source": "sql",
            "action_data": {"error": str(e)},
        }
        yield {"type": "token", "content": "I encountered an issue retrieving that data. Please try rephrasing your question or ask something else."}
        return

    result_text = f"SQL Query: {sql}\n\nResults ({len(result['rows'])} rows):\n"
    for row in result["rows"][:20]:
        result_text += str(row) + "\n"

    yield {
        "type": "thought",
        "content": "Summarizing results...",
        "action_type": "synthesizing",
        "action_source": "sql",
        "action_data": {"sql": sql, "row_count": len(result["rows"])},
    }
    summary_prompt = f"Based on the following database query results, answer the user's question.\n\nQuestion: {message}\n\n{result_text}"

    async for chunk in generate_chat_response_stream(client, summary_prompt, history, images=images, system_prompt=SQL_SUMMARY_SYSTEM_PROMPT):
        yield {"type": "token", "content": chunk}
