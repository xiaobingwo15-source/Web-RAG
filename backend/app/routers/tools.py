import logging
from fastapi import APIRouter, Depends, HTTPException
from app.middleware.auth import get_current_user
from app.models.tools import SqlQueryRequest, SqlQueryResponse, WebSearchRequest, WebSearchResponse, WebSearchResult
from app.services.gemini import get_llm_client
from app.services.sql_agent import generate_sql
from app.services.sql_engine import get_schema_description, execute_readonly_sql
from app.services.web_search import search_web

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sql", response_model=SqlQueryResponse)
async def sql_query(request: SqlQueryRequest, user=Depends(get_current_user)):
    client = get_llm_client()
    schema = get_schema_description()

    sql = await generate_sql(client, request.question, schema)
    logger.info(f"Generated SQL: {sql}")

    try:
        result = execute_readonly_sql(sql)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"SQL execution failed: {e}")

    return SqlQueryResponse(
        question=request.question,
        generated_sql=sql,
        results=result["rows"],
        columns=result["columns"],
    )


@router.post("/search", response_model=WebSearchResponse)
async def web_search_endpoint(request: WebSearchRequest, user=Depends(get_current_user)):
    results = await search_web(request.query, request.max_results)
    return WebSearchResponse(
        query=request.query,
        results=[
            WebSearchResult(title=r["title"], url=r["url"], content=r["content"])
            for r in results
        ],
    )
