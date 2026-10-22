"""Ordinary tools = capabilities. Skills (skills/) tell the model WHEN and HOW to use them."""

from langchain_core.tools import tool

# Fake order database (same orders as sample5's skills server).
ORDERS = {
    "A100": {"status": "delivered", "total": 80, "age_days": 12},
    "A200": {"status": "delivered", "total": 120, "age_days": 45},
    "A300": {"status": "delivered", "total": 900, "age_days": 5},
    "A400": {"status": "final_sale", "total": 40, "age_days": 3},
}


@tool
def lookup_order(order_id: str) -> dict | str:
    """Look up an order's status, total (USD) and age in days."""
    return ORDERS.get(order_id.upper(), f"No order {order_id!r}.")


@tool
def calculator(expression: str) -> str:
    """Evaluate a simple arithmetic expression, e.g. '720 * 0.15'."""
    if not set(expression) <= set("0123456789+-*/(). "):
        return "Only numbers and + - * / ( ) are allowed."
    return str(eval(expression))  # safe: charset restricted above


BASIC_TOOLS = [lookup_order, calculator]
