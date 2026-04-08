import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.redis_client import close_redis
from app.routers import router as api_router
from app.startup import warm_pricing_cache

logging.basicConfig(level=logging.INFO)
svc_logger = logging.getLogger("pay-per-use")


@asynccontextmanager
async def lifespan(app: FastAPI):
    svc_logger.info("Starting pay-per-use service...")
    await init_db()
    await warm_pricing_cache()
    yield
    await close_redis()


app = FastAPI(title="Pay Per Use Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "pay-per-use"}
