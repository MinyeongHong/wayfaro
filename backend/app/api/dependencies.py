import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import settings

bearer = HTTPBearer(auto_error=False)


def require_ingestion_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    configured = settings.ingestion_admin_token
    if configured is None or not configured.get_secret_value().strip():
        raise HTTPException(status_code=503, detail="Ingestion administration is not configured")
    if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(), configured.get_secret_value().encode()):
        raise HTTPException(status_code=401, detail="Invalid administrator credentials",
                            headers={"WWW-Authenticate": "Bearer"})
