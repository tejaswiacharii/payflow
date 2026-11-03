import os
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from fastapi.responses import RedirectResponse
from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers the tables on Base)
from app.database import Base, engine, get_db
from app.routers import auth, notifications, transactions, transfers, wallet

@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="PayFlow", version="0.1.0", lifespan=lifespan)
allowed_origins = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    expose_headers=["Idempotent-Replayed"],
)
app.include_router(auth.router)
app.include_router(wallet.router)
app.include_router(transfers.router)
app.include_router(transactions.router)
app.include_router(notifications.router)

@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")
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