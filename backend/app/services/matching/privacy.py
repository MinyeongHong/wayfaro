"""Bound request size and suppress private validation values / exception details."""
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def is_private(path):
    return path == "/api/v1/analyses" or path.startswith("/api/v1/analyses/")


async def private_validation_error(request, exc: RequestValidationError):
    from fastapi.exception_handlers import request_validation_exception_handler
    if not is_private(request.url.path):
        return await request_validation_exception_handler(request, exc)
    return JSONResponse(status_code=422, content={"detail": [
        {"loc": [part if isinstance(part, int) or part in
                 {"body", "path", "analysis_id", "cv_text", "jd_text", "consent", "policy_version"}
                 else "field" for part in error["loc"]], "type": error["type"], "msg": "Invalid request field"}
        for error in exc.errors()]}, headers={"Cache-Control": "no-store"})


class PrivateAnalysisMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not is_private(scope["path"]):
            return await self.app(scope, receive, send)
        started = False

        async def private_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [(key, value) for key, value in message.get("headers", [])
                                      if key.lower() != b"cache-control"] + [(b"cache-control", b"no-store")]
            await send(message)

        if scope["method"] == "POST":
            content = bytearray()
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                content.extend(message.get("body", b""))
                if len(content) > 350000:
                    return await JSONResponse({"detail": "Request too large"}, status_code=413)(scope, receive, private_send)
                if not message.get("more_body", False):
                    break
            delivered = False
            original_receive = receive

            async def replay():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": bytes(content), "more_body": False}
                return await original_receive()
            receive = replay
        try:
            await self.app(scope, receive, private_send)
        except Exception:
            # Never log SQL parameters, raw provider responses, CVs or JDs.
            if not started:
                await JSONResponse({"detail": "Analysis request failed"}, status_code=500)(scope, receive, private_send)
