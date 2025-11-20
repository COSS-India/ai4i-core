from fastapi import FastAPI
from contextlib import asynccontextmanager
from logger import logger
from db_connection import create_tables
from routers.router_admin import router_admin
from routers.router_details import router_details
import uvicorn

from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException, Request

# -----------------------------
# Lifespan Event Handler (replaces @app.on_event)
# -----------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ---- Startup ----
    logger.info("Starting FastAPI app initialization...")
    create_tables()
    logger.info("Database tables verified or created (if not existing).")

    yield  # ⬅️ everything before this runs at startup; everything after runs at shutdown

    # ---- Shutdown ----
    logger.info("Shutting down FastAPI app...")



app = FastAPI(
    title="Model Management Service API",
    version="1.0.0",
    description="API for creating and managing models",
    lifespan=lifespan,  # ✅ use lifespan instead of @on_event
)

# Register routers
app.include_router(router_admin)
app.include_router(router_details)



# -----------------------------
# Global Exception Handlers
# -----------------------------
@app.exception_handler(401)
async def unauthorized_handler(_, __):
    logger.warning("Unauthorized access attempt detected")
    return JSONResponse(status_code=401, content={"detail": {"message": "Unauthorized"}})


@app.exception_handler(403)
async def forbidden_handler(_, __):
    logger.warning("Forbidden access attempt detected")
    return JSONResponse(status_code=403, content={"detail": {"message": "Forbidden"}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error at {request.url.path}: {exc.errors()}")
    errors = []
    for err in exc.errors():
        errors.append({
            "loc": list(err.get("loc", [])),
            "msg": err.get("msg", ""),
            "type": err.get("type", "")
        })
    return JSONResponse(status_code=422, content={"detail": errors})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logger.error(f"HTTPException at {request.url.path}: {exc.detail}")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": {"kind": "UnhandledError", "message": str(exc)}}
    )





if __name__ == "__main__":
    logger.info(" Starting FastAPI server on http://0.0.0.0:8000 ...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
