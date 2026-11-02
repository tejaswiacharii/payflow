from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import models  # noqa: F401  (registers the tables on Base)
from app.database import Base, engine
from app.routers import auth


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="PayFlow", version="0.1.0", lifespan=lifespan)
app.include_router(auth.router)