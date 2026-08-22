"""
Seed script for Order-to-Cash Orchestrator
Populates MongoDB with Indian e-commerce inventory and customer data.

Includes:
    - 6 products with quantity_reserved field
    - 6 customers (4 old + 2 new: Vijay Sales, Amazon India Seller Hub)
    - Clears orders, invoices, backorders, workflows, workflow_events
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from config import settings


async def seed_database():
    print(f"Connecting to MongoDB at {settings.MONGODB_URI[:40]}...")
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]

    print("Dropping existing collections...")
    await db.inventory.drop()
    await db.customers.drop()
    await db.orders.drop()
    await db.invoices.drop()
    await db.backorders.drop()
    await db.workflows.drop()
    await db.workflow_events.drop()

    # ═══════════════════════════════════════════
    # INVENTORY — Indian E-Commerce Products (₹)
    # ═══════════════════════════════════════════
    inventory = [
        {
            "_id": "SKU-1001",
            "name": "boAt Airdopes 141 (Wireless Earbuds)",
            "category": "Electronics",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 50,
            "unit_cost": 799,
            "unit_price": 1299,
            "warehouse": "Mumbai-WH"
        },
        {
            "_id": "SKU-1002",
            "name": "Samsung Galaxy M14 5G (128GB)",
            "category": "Smartphones",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 30,
            "unit_cost": 10999,
            "unit_price": 13490,
            "warehouse": "Hyderabad-WH"
        },
        {
            "_id": "SKU-1003",
            "name": "Noise ColorFit Pro 4 Smart Watch",
            "category": "Wearables",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 40,
            "unit_cost": 2499,
            "unit_price": 3999,
            "warehouse": "Delhi-WH"
        },
        {
            "_id": "SKU-1004",
            "name": "Ambrane 20000mAh Power Bank",
            "category": "Accessories",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 60,
            "unit_cost": 649,
            "unit_price": 999,
            "warehouse": "Bangalore-WH"
        },
        {
            "_id": "SKU-1005",
            "name": "HP Victus 15 Gaming Laptop (i5, RTX 3050)",
            "category": "Laptops",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 10,
            "unit_cost": 52999,
            "unit_price": 62990,
            "warehouse": "Chennai-WH"
        },
        {
            "_id": "SKU-1006",
            "name": "Levi's Men's 511 Slim Fit Jeans",
            "category": "Fashion",
            "quantity_available": 500,
            "quantity_reserved": 0,
            "reorder_point": 50,
            "unit_cost": 1200,
            "unit_price": 2499,
            "warehouse": "Mumbai-WH"
        },
    ]

    # ═══════════════════════════════════════════
    # CUSTOMERS — Indian Businesses (6 total)
    # ═══════════════════════════════════════════
    customers = [
        {
            "_id": "CUST-101",
            "name": "Reliance Digital Stores",
            "email": "procurement@reliancedigital.in",
            "phone": "+91-22-4478-1000",
            "address": "Navi Mumbai, Maharashtra 400710",
            "gst_number": "27AABCR1718E1ZM",
            "credit_limit": 500000,
            "risk_tier": "low",
            "total_orders": 45,
            "overdue_payments": 0,
            "payment_terms": "NET30"
        },
        {
            "_id": "CUST-102",
            "name": "Croma Electronics",
            "email": "orders@croma.com",
            "phone": "+91-22-6789-0000",
            "address": "Infinity IT Park, Malad West, Mumbai 400064",
            "gst_number": "27AABCC4568F2ZQ",
            "credit_limit": 300000,
            "risk_tier": "medium",
            "total_orders": 2,
            "overdue_payments": 1,
            "payment_terms": "NET15"
        },
        {
            "_id": "CUST-103",
            "name": "Poorvika Mobiles",
            "email": "bulk@poorvika.com",
            "phone": "+91-44-4567-8900",
            "address": "T. Nagar, Chennai, Tamil Nadu 600017",
            "gst_number": "33AABCP7890G1ZR",
            "credit_limit": 200000,
            "risk_tier": "low",
            "total_orders": 18,
            "overdue_payments": 0,
            "payment_terms": "NET30"
        },
        {
            "_id": "CUST-201",
            "name": "TechBazaar Online (New Seller)",
            "email": "contact@techbazaar.in",
            "phone": "+91-80-9999-1234",
            "address": "Koramangala, Bangalore, Karnataka 560034",
            "gst_number": "29AABCT1234H1ZS",
            "credit_limit": 50000,
            "risk_tier": "high",
            "total_orders": 0,
            "overdue_payments": 0,
            "payment_terms": "PREPAID"
        },
        {
            "_id": "CUST-104",
            "name": "Vijay Sales",
            "email": "wholesale@vijaysales.com",
            "phone": "+91-22-2674-1100",
            "address": "Mahim, Mumbai, Maharashtra 400016",
            "gst_number": "27AABCV5678D1ZT",
            "credit_limit": 400000,
            "risk_tier": "medium",
            "total_orders": 12,
            "overdue_payments": 0,
            "payment_terms": "NET30"
        },
        {
            "_id": "CUST-105",
            "name": "Amazon India Seller Hub",
            "email": "seller-ops@amazon.in",
            "phone": "+91-80-4646-4646",
            "address": "World Trade Center, Brigade Gateway, Bangalore 560055",
            "gst_number": "29AABCA9876E1ZU",
            "credit_limit": 2000000,
            "risk_tier": "low",
            "total_orders": 120,
            "overdue_payments": 0,
            "payment_terms": "NET45"
        },
    ]

    print("Inserting seed data...")
    await db.inventory.insert_many(inventory)
    await db.customers.insert_many(customers)

    print("Seed complete!")
    print(f"  [OK] {len(inventory)} products inserted")
    print(f"  [OK] {len(customers)} customers inserted")
    print(f"  [OK] orders, invoices, backorders, workflows, workflow_events cleared")


if __name__ == "__main__":
    asyncio.run(seed_database())
