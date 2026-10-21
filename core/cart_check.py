"""Utilities for comparing a verified bill listing with a TinyFish cart check."""

from core import bill, browser_cart, tf

MAX_STEPS = 12


def options(parts, live, choice):
    """Return verified chosen listings as {label: (url, expected_unit_price)}."""
    out = {}
    for part in parts.values():
        if part.get("none"):
            continue
        url = bill.chosen_url(part["id"], live, choice or {})
        offer = next(
            (offer for offer in bill.offers_for(part["id"], live) if offer["url"] == url),
            None,
        ) if url else None
        if offer:
            out[f"{part['name']} · {bill.vendor(url)}"] = (url, float(offer["price"]))
    return out


def compare(expected, result, tol=0.02):
    """Return the cart-price verdict and explanation."""
    result_data = (result or {}).get("result") or {}
    if result_data.get("added_to_cart") is False:
        if result_data.get("in_stock") is False:
            return (
                "not added",
                "Nothing was added to the cart: the shop's product page shows this item as out of stock. "
                "The listed price may still be right, but you cannot buy it right now. Check availability before ordering.",
            )
        return (
            "not added",
            "Nothing could be added to the cart (the item may be unavailable or need a choice we did not make, such as a variant).",
        )
    actual = result_data.get("unit_price_inr")
    if not isinstance(actual, (int, float)) or isinstance(actual, bool) or actual <= 0:
        return "not read", "The agent did not report a unit price."
    if abs(actual - expected) <= max(2.0, tol * expected):
        return "match", f"Cart unit price {bill.inr(actual)} matches the bill ({bill.inr(expected)})."
    return (
        "differs",
        f"Cart unit price {bill.inr(actual)} differs from the bill ({bill.inr(expected)}). "
        "Trust the shop's cart and recheck the listing.",
    )


def run(state, url):
    """Run a cart check and store either its result or the surfaced error."""
    store = state.setdefault("agent", {})
    try:
        store[url] = browser_cart.check(url, agent=lambda target: tf.agent(target, max_steps=MAX_STEPS))
    except Exception as error:
        store[url] = dict(status="ERROR", error=str(error)[:200])
    return store[url]


def executor_line(result):
    """Describe which TinyFish executor ran and which limits were applied."""
    method = result.get("method")
    if not method:
        return ""
    line = f"{browser_cart.icon(method)} Executed by the {browser_cart.label(method)}"
    if result.get("fallback_reason"):
        line += f" (fallback: {result['fallback_reason']})"
    if method == "agent" and "mode" in result:
        notes = []
        if result.get("mode") == "default":
            notes.append("default mode, because strict mode is not enabled on this TinyFish account")
        if result.get("step_cap") is None:
            notes.append(
                f"NO step cap, because this TinyFish account cannot set one; "
                f"it used {result.get('num_of_steps', 'n/a')} steps"
            )
        if result.get("time_cap") is None:
            notes.append("no time cap either")
        if notes:
            line += " · " + "; ".join(notes)
    return line
