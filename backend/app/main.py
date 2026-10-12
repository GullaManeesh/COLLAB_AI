from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import PyMongoError

from app.config.settings import settings
from app.database.indexes import create_indexes
from app.database.mongodb import (
    close_mongodb_connection,
    connect_to_mongodb,
    get_database,
)
from app.routes.auth_routes import router as auth_router
from app.routes.workspace_routes import router as workspace_router
from app.routes.invitation_routes import router as invitation_router
from app.routes.notification_routes import router as notification_router
from app.routes.document_routes import router as document_router
from app.routes.chat_routes import router as chat_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await connect_to_mongodb()
        await create_indexes()
        yield
    finally:
        await close_mongodb_connection()


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for the CollabAI collaborative workspace",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.get("/")
async def root():
    return {"message": "Welcome to CollabAI API", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "CollabAI backend"}


@app.get("/health/db")
async def health_db():
    try:
        await get_database().command("ping")
        return {"status": "healthy", "database": settings.MONGODB_DB_NAME}
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc


# Application Routers
app.include_router(auth_router)
app.include_router(workspace_router, prefix="/api")
app.include_router(invitation_router, prefix="/api")
app.include_router(notification_router, prefix="/api")
app.include_router(document_router, prefix="/api")
app.include_router(chat_router, prefix="/api")