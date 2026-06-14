import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status
from app.config import Settings
from app.middleware.auth import get_current_user
from app.models.tools import SqlQueryRequest, SqlQueryResponse, WebSearchRequest, WebSearchResponse, WebSearchResult
from app.services.audit import log_operation
from app.services.gemini import get_llm_client
from app.services.sql_agent import generate_sql
from app.services.sql_engine import get_schema_description, execute_readonly_sql
from app.services.web_search import search_web

logger = logging.getLogger(__name__)

router = APIRouter()


def _verify_admin_tool_access(user) -> None:
    if user.role != "admin" or not user.tenant_id or user.status != "approved":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    if not Settings().sql_tools_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin tools are disabled",
        )


@router.post("/sql", response_model=SqlQueryResponse)
async def sql_query(request_body: SqlQueryRequest, request: Request, user=Depends(get_current_user)):
    _verify_admin_tool_access(user)
    client = get_llm_client()
    schema = get_schema_description()

    sql = await generate_sql(client, request_body.question, schema)
    logger.info(f"Generated SQL: {sql}")

    try:
        result = execute_readonly_sql(sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL execution failed: {e}")
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="tool.sql.execute",
        resource_type="sql_tool",
        resource_id=None,
        metadata={
            "question": request_body.question,
            "generated_sql": sql,
            "row_count": len(result["rows"]),
        },
        request=request,
    )

    return SqlQueryResponse(
        question=request_body.question,
        generated_sql=sql,
        results=result["rows"],
        columns=result["columns"],
    )


@router.post("/search", response_model=WebSearchResponse)
async def web_search_endpoint(request_body: WebSearchRequest, request: Request, user=Depends(get_current_user)):
    _verify_admin_tool_access(user)
    results = await search_web(request_body.query, request_body.max_results)
    log_operation(
        tenant_id=user.tenant_id,
        actor_user_id=user.id,
        actor_email=getattr(user, "email", None),
        actor_role=user.role,
        action="tool.search.execute",
        resource_type="web_search_tool",
        resource_id=None,
        metadata={"query": request_body.query, "result_count": len(results)},
        request=request,
    )
    return WebSearchResponse(
        query=request_body.query,
        results=[
            WebSearchResult(title=r["title"], url=r["url"], content=r["content"])
            for r in results
        ],
    )
