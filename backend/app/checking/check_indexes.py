
import asyncio

from app.database.mongodb import (
    connect_to_mongodb,
    close_mongodb_connection,
    get_database,
)


async def main():
    try:
        await connect_to_mongodb()
        db = get_database()

        collections = [
            "workspaces",
            "workspace_members",
            "messages",
            "documents",
            "invitations",
        ]

        for name in collections:
            indexes = await db[name].index_information()
            print(f"\n{name}:")
            for index_name, details in indexes.items():
                print(f"  {index_name}: {details['key']}")

    finally:
        await close_mongodb_connection()


if __name__ == "__main__":
    asyncio.run(main())
