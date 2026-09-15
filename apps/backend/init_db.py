import asyncio
from api.db import init_db
from api.models import User, TranslationRequest  # Ensure models are imported to register with Base

async def main():
    print("Initializing database schema...")
    await init_db()
    print("Database schema initialized successfully.")

if __name__ == "__main__":
    asyncio.run(main())
