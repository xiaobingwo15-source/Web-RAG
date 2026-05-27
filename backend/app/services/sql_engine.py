import re
import logging
from app.services.supabase import get_supabase_client

logger = logging.getLogger(__name__)

BLOCKED_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE)\b',
    re.IGNORECASE,
)


def get_schema_description() -> str:
    db = get_supabase_client()
    result = db.table("table_schema_info").select("*").execute()
    lines = ["Tables:"]
    current_table = None
    for row in result.data:
        if row["table_name"] != current_table:
            current_table = row["table_name"]
            lines.append(f"\n{current_table}:")
        lines.append(f"  {row['column_name']} ({row['data_type']}){' NULL' if row['is_nullable'] == 'YES' else ' NOT NULL'}")
    return "\n".join(lines)


def execute_readonly_sql(sql: str) -> dict:
    sql = sql.strip().rstrip(";")

    if not sql.upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    if BLOCKED_KEYWORDS.search(sql):
        raise ValueError("Query contains blocked keywords")

    db = get_supabase_client()
    result = db.rpc("exec_readonly_sql", {"query_text": sql}).execute()

    if not result.data:
        return {"columns": [], "rows": []}

    columns = list(result.data[0].keys()) if result.data else []
    return {"columns": columns, "rows": result.data}
