"""Conservative menu-item type checks shared by QA and scoring."""

NON_PIZZA_NAME_TERMS = (
    "sauce", "sachet", "packet", "cola", "fanta", "sprite", "pepsi",
    "drink", "beverage", "wings", "poppers", "fries", "breadstick",
    "scroll", "cookie", "dessert", "sandwich", "burger", "papadia",
    "papadias", "salad", "pasta", "lasagna", "dipping",
)


def is_likely_non_pizza_name(name: str) -> bool:
    value = (name or "").casefold()
    return any(term in value for term in NON_PIZZA_NAME_TERMS)
