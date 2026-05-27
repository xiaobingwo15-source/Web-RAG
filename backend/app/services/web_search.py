import logging
import httpx
from app.config import Settings

logger = logging.getLogger(__name__)


async def search_web(query: str, max_results: int = 5) -> list[dict]:
    settings = Settings()
    tavly_key = settings.get_tavly_api_key
    if not tavly_key:
        logger.warning("TAVLY_API_KEY not configured")
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": tavly_key,
                "query": query,
                "max_results": max_results,
                "include_answer": True,
            },
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for r in data.get("results", []):
        results.append({
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        })
    return results
