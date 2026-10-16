import asyncio
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
from app.routes.agent_routes import router as agent_router, recover_stale_agent_runs
from app.services.embedding_service import initialize_embedding_model_async
from app.services.document_service import (
    monitor_interrupted_document_uploads,
    recover_interrupted_document_uploads,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    document_recovery_task = None
    try:
        await connect_to_mongodb()
        await create_indexes()
        await recover_interrupted_document_uploads()
        document_recovery_task = asyncio.create_task(
            monitor_interrupted_document_uploads(),
            name="document-upload-recovery",
        )
        await recover_stale_agent_runs()
        # Warm the local ONNX model once per process. The API remains available
        # if model download/cache access fails; upload requests keep documents
        # marked failed and can retry after network/cache recovery.
        await initialize_embedding_model_async()
        yield
    finally:
        if document_recovery_task is not None:
            document_recovery_task.cancel()
            try:
                await document_recovery_task
            except asyncio.CancelledError:
                pass
        await close_mongodb_connection()


app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API for the CollabAI collaborative workspace",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(dict.fromkeys([
        settings.FRONTEND_URL.rstrip("/"),
        "https://www.collabai.online",
        "https://collabai.online",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ])),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
app.include_router(agent_router, prefix="/api")
