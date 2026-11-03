from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers the tables on Base)
from app.database import Base, engine, get_db
from app.routers import auth, wallet


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="PayFlow", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(wallet.router)


@app.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"status": "unhealthy", "database": "unavailable"},
        )
    return {"status": "ok", "database": "connected"}