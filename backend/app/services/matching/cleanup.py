"""Optional one-shot cleanup; normal worker runs the same cleanup periodically."""
from app.db.session import SessionLocal
from .storage import cleanup_expired

if __name__ == "__main__":
    while cleanup_expired(SessionLocal):
        pass
