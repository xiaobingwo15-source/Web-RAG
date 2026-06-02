import time
from collections import defaultdict, deque

from fastapi import HTTPException, status

_requests: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: int) -> None:
    now = time.monotonic()
    cutoff = now - window_seconds
    bucket = _requests[key]

    while bucket and bucket[0] < cutoff:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit reached. Please wait a moment and try again.",
        )

    bucket.append(now)
