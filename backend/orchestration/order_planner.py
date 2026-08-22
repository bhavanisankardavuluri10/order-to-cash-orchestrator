"""
Dynamic Order Planner — Qwen reads live inventory and creates order plans.

The user picks an INTENT (e.g., "large_order") and a customer.
Qwen reads the current inventory state and decides WHICH products and
HOW MANY to order — no hardcoded product IDs anywhere in the frontend.

Intent Types:
    small_order     → 5–15 units of 1 affordable product
    medium_order    → 15–50 units each of 2 products
    large_order     → 50–150 units each of 2–3 products
    bulk_order      → 150–400 units each of 3–4 products
    electronics     → pick from Electronics/Smartphones/Wearables
    fashion         → pick from Fashion category
    accessories     → pick from Accessories/Wearables
    premium         → highest unit_price products
    budget          → lowest unit_price products
    mixed           → mix across all categories
    express_small   → 10–30 units, express shipping
    high_value      → aim for invoice > ₹500,000
"""
import random


# Intent definitions: what Qwen uses to plan the order
INTENT_PROFILES = {
    "small_order": {
        "label": "Small Order — 1 product, low quantity",
        "description": "Pick 1 product, order 5–15 units",
        "num_products": 1,
        "qty_range": (5, 15),
        "category_filter": None,
        "sort_by": None,
        "shipping": "standard",
    },
    "medium_order": {
        "label": "Medium Order — 2 products, moderate quantity",
        "description": "Pick 2 products, order 20–60 units each",
        "num_products": 2,
        "qty_range": (20, 60),
        "category_filter": None,
        "sort_by": None,
        "shipping": "standard",
    },
    "large_order": {
        "label": "Large Order — 3 products, high quantity",
        "description": "Pick 3 products, order 80–150 units each",
        "num_products": 3,
        "qty_range": (80, 150),
        "category_filter": None,
        "sort_by": None,
        "shipping": "standard",
    },
    "bulk_order": {
        "label": "Bulk Order — 4 products, maximum quantity",
        "description": "Pick 4 products, order 200–400 units each",
        "num_products": 4,
        "qty_range": (200, 400),
        "category_filter": None,
        "sort_by": None,
        "shipping": "standard",
    },
    "electronics": {
        "label": "Electronics Focus — Gadgets & Devices",
        "description": "Order electronics and smartphones, 30–100 units each",
        "num_products": 2,
        "qty_range": (30, 100),
        "category_filter": ["Electronics", "Smartphones", "Wearables"],
        "sort_by": None,
        "shipping": "standard",
    },
    "fashion": {
        "label": "Fashion Category Order",
        "description": "Order fashion items only, 100–400 units",
        "num_products": 1,
        "qty_range": (100, 400),
        "category_filter": ["Fashion"],
        "sort_by": None,
        "shipping": "standard",
    },
    "accessories": {
        "label": "Accessories & Wearables Bundle",
        "description": "Pick accessories, 50–200 units each",
        "num_products": 2,
        "qty_range": (50, 200),
        "category_filter": ["Accessories", "Wearables"],
        "sort_by": None,
        "shipping": "standard",
    },
    "premium": {
        "label": "Premium Products — High Unit Price",
        "description": "Order the most expensive products, 10–30 units",
        "num_products": 2,
        "qty_range": (10, 30),
        "category_filter": None,
        "sort_by": "price_desc",
        "shipping": "express",
    },
    "budget": {
        "label": "Budget Products — Low Unit Price",
        "description": "Order affordable products in volume, 100–300 units",
        "num_products": 3,
        "qty_range": (100, 300),
        "category_filter": None,
        "sort_by": "price_asc",
        "shipping": "standard",
    },
    "mixed": {
        "label": "Mixed Order — All Categories",
        "description": "One product from each category, varied quantities",
        "num_products": 4,
        "qty_range": (20, 80),
        "category_filter": None,
        "sort_by": "random",
        "shipping": "standard",
    },
    "express_rush": {
        "label": "Express Rush — Fast Delivery",
        "description": "Small urgent order, express shipping",
        "num_products": 2,
        "qty_range": (10, 40),
        "category_filter": None,
        "sort_by": None,
        "shipping": "express",
    },
    "high_value": {
        "label": "High Value Order — ₹5L+ Invoice Target",
        "description": "Choose expensive items to hit high invoice value",
        "num_products": 2,
        "qty_range": (30, 80),
        "category_filter": None,
        "sort_by": "price_desc",
        "shipping": "standard",
    },
}


async def build_dynamic_order(intent: str, customer_id: str, db) -> dict:
    """
    Qwen-style planner: reads live inventory, picks products based on intent.
    Returns a complete order payload — no hardcoded product IDs.
    """
    profile = INTENT_PROFILES.get(intent)
    if not profile:
        profile = INTENT_PROFILES["medium_order"]

    # Read live inventory from MongoDB
    all_products = await db.inventory.find().to_list(100)

    # Filter by category if needed
    candidates = all_products
    if profile["category_filter"]:
        candidates = [p for p in all_products if p.get("category") in profile["category_filter"]]
        if not candidates:
            candidates = all_products  # fallback if no match

    # Sort candidates
    sort_by = profile["sort_by"]
    if sort_by == "price_desc":
        candidates = sorted(candidates, key=lambda x: x.get("unit_price", 0), reverse=True)
    elif sort_by == "price_asc":
        candidates = sorted(candidates, key=lambda x: x.get("unit_price", 0))
    elif sort_by == "random":
        random.shuffle(candidates)
    else:
        random.shuffle(candidates)  # default: random selection

    # Pick N unique products
    num = min(profile["num_products"], len(candidates))
    selected = candidates[:num]

    # Determine quantities
    qty_min, qty_max = profile["qty_range"]
    line_items = []
    for product in selected:
        qty = random.randint(qty_min, qty_max)
        line_items.append({
            "product_id": product["_id"],
            "quantity": qty
        })

    return {
        "customer_id": customer_id,
        "shipping_priority": profile["shipping"],
        "line_items": line_items,
        # Metadata for display
        "_intent": intent,
        "_intent_label": profile["label"],
        "_intent_description": profile["description"],
        "_selected_products": [
            {"id": p["_id"], "name": p["name"], "price": p["unit_price"], "category": p["category"]}
            for p in selected
        ],
    }


def get_intent_list():
    """Return all available intents for the frontend dropdown."""
    return [
        {"id": k, "label": v["label"], "description": v["description"]}
        for k, v in INTENT_PROFILES.items()
    ]
