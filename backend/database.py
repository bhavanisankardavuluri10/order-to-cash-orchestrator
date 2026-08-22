"""
Database — MongoDB connection management with index creation.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


class Database:
    client: AsyncIOMotorClient = None
    db = None

db_config = Database()


async def connect_to_mongo():
    db_config.client = AsyncIOMotorClient(settings.MONGODB_URI)
    db_config.db = db_config.client[settings.DATABASE_NAME]
    print(f"[OK] Connected to MongoDB: {settings.DATABASE_NAME}")

    # Create indexes for performance
    await _create_indexes()


async def _create_indexes():
    """Create indexes on collections for query performance."""
    db = db_config.db
    try:
        await db.orders.create_index("workflow_id")
        await db.orders.create_index("customer_id")
        await db.orders.create_index("created_at")
        await db.invoices.create_index("order_id")
        await db.invoices.create_index("workflow_id")
        await db.backorders.create_index("order_id")
        await db.backorders.create_index("workflow_id")
        await db.workflow_events.create_index("workflow_id")
        await db.workflow_events.create_index("timestamp")
        await db.workflows.create_index("workflow_id")
        print("  [OK] Indexes created/verified")
    except Exception as e:
        print(f"  [WARN] Index creation warning: {e}")


async def close_mongo_connection():
    if db_config.client:
        db_config.client.close()
        print("MongoDB connection closed.")


def get_db():
    return db_config.db
