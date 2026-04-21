from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class BearerTokenMiddleware:
    """ASGI middleware: validates Authorization: Bearer or X-Api-Key header.
    Pass-through when settings.api_keys is empty (dev mode).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        from memory_service.config import settings

        if not settings.api_keys:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        token = None
        auth = headers.get(b"authorization", b"").decode()
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
        if not token:
            token = headers.get(b"x-api-key", b"").decode() or None

        if token and token in settings.api_keys:
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            {"detail": "Invalid or missing API key"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
        await response(scope, receive, send)
