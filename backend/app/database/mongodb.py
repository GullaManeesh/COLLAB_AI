from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from app.config.settings import settings


client: AsyncMongoClient | None = None


async def connect_to_mongodb() -> None:
    global client

    if not settings.MONGODB_URI:
        raise RuntimeError("MONGODB_URI is not set in the environment variables.")

    new_client = AsyncMongoClient(
        settings.MONGODB_URI,
        maxPoolSize=settings.MONGODB_MAX_POOL_SIZE,
        minPoolSize=settings.MONGODB_MIN_POOL_SIZE,
        serverSelectionTimeoutMS=settings.MONGODB_SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=settings.MONGODB_CONNECT_TIMEOUT_MS,
        appname="CollabAI",
    )
    try:
        await new_client.admin.command("ping")
    except PyMongoError as exc:
        await new_client.close()
        raise RuntimeError(f"Failed to connect to MongoDB: {exc}") from exc

    client = new_client


async def close_mongodb_connection() -> None:
    global client

    if client is not None:
        await client.close()
        client = None


def get_database():
    if client is None:
        raise RuntimeError("MongoDB is not connected.")
    return client[settings.MONGODB_DB_NAME]
