# memory_service/auth.py

from fastapi import HTTPException, Request, status


_OPEN_PATHS: frozenset[str] = frozenset({
    "/health",
    "/.well-known/oauth-protected-resource",
    "/.well-known/oauth-protected-resource/mcp",
    "/mcp/.well-known/oauth-protected-resource",
})


async def verify_api_key(request: Request) -> None:
    """FastAPI dependency that enforces bearer token / API key authentication.

    Accepts:
      - Authorization: Bearer <token>
      - X-Api-Key: <token>  (case-insensitive header name)

    Paths in _OPEN_PATHS (e.g. /health) are always permitted without a token.
    If API_KEYS is empty the service runs unauthenticated (dev / localhost mode).
    Returns 401 with WWW-Authenticate: Bearer on failure.
    """
    if request.url.path in _OPEN_PATHS:
        return

    from memory_service.config import settings  # deferred to avoid circular import at module load

    if not settings.api_keys:
        return  # no keys configured → open (dev / localhost mode)

    token: str | None = None

    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()

    if not token:
        token = request.headers.get("X-Api-Key") or request.headers.get("X-API-Key")

    if token and token in settings.api_keys:
        return

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "Bearer"},
    )
