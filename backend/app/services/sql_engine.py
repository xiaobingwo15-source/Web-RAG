import re
import logging
from app.services.supabase import get_supabase_client

logger = logging.getLogger(__name__)

BLOCKED_KEYWORDS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|EXEC|EXECUTE|CALL|COPY)\b',
    re.IGNORECASE,
)
ALLOWED_TABLES = {"ie_sales", "ie_employees"}
TABLE_REF_RE = re.compile(r'\b(?:FROM|JOIN)\s+("?[\w.]+"?)', re.IGNORECASE)


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
    if ";" in sql or "--" in sql or "/*" in sql or "*/" in sql:
        raise ValueError("Only a single SELECT statement is allowed")

    if BLOCKED_KEYWORDS.search(sql):
        raise ValueError("Query contains blocked keywords")
    referenced_tables = {
        match.group(1).replace('"', "").split(".")[-1].lower()
        for match in TABLE_REF_RE.finditer(sql)
    }
    if not referenced_tables:
        raise ValueError("Query must reference an allowed table")
    unexpected_tables = referenced_tables - ALLOWED_TABLES
    if unexpected_tables:
        raise ValueError(f"Query references disallowed tables: {', '.join(sorted(unexpected_tables))}")

    db = get_supabase_client()
    result = db.rpc("exec_readonly_sql", {"query_text": sql}).execute()

    if not result.data:
        return {"columns": [], "rows": []}

    columns = list(result.data[0].keys()) if result.data else []
    return {"columns": columns, "rows": result.data}
