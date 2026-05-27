from pydantic import BaseModel


class SqlQueryRequest(BaseModel):
    question: str


class SqlQueryResponse(BaseModel):
    question: str
    generated_sql: str
    results: list[dict]
    columns: list[str]


class WebSearchRequest(BaseModel):
    query: str
    max_results: int = 5


class WebSearchResult(BaseModel):
    title: str
    url: str
    content: str


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult]
