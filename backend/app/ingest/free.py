"""Where "is it free?" is decided. One function per source; the rules differ and are kept as they were.

| function        | source                         | says free when                                                        |
|-----------------|--------------------------------|-----------------------------------------------------------------------|
| jsonld_is_free  | structured data of an event    | isAccessibleForFree is true, or every price is 0; False if any price  |
|                 |                                | is above 0; None with no prices                                       |
| hint_is_free    | model on a post or page (text) | the model said so, "free" is in the text, no price above 0; a "not    |
|                 |                                | free" needs a price or a "$" in the text                              |
| page_price_free | model on a ticket page         | the model said so, FREE_ENTRY matches the text, no price above 0; a   |
|                 |                                | $0 price without FREE_ENTRY wording is dropped                        |
| site_is_free    | model on a venue's site        | the model said true and the pages match "free" or "no cover"          |
"""
import re

# Wording that says getting in costs nothing ("free donuts" or "free parking" does not)
FREE_ENTRY = re.compile(
    r"\bno\s+cover\b|\$\s?0(\.00?)?\b|\bfree\s+(entry|admission|event|to\s+(attend|enter|join|rsvp)|rsvp|tickets?|"
    r"general\s+admission|before|until|for\s+all|and\s+open|of\s+charge)\b|\bfree\s*[.!]|"
    r"\b(admission|entry|cover|price|cost|tickets?|rsvp)\s*(is|:|-)?\s*free\b|\bcomplimentary\s+(entry|admission)\b|"
    r"\bfree$", re.I | re.M)


def jsonld_is_free(accessible_for_free, prices: list[float]) -> bool | None:
    """schema.org: isAccessibleForFree, else the offer prices."""
    if accessible_for_free in (True, "true", "True"):
        return True
    if prices and max(prices) == 0:
        return True
    if prices:
        return False
    return None


def hint_is_free(is_free, price_min, price_max, text: str):
    """The model's is_free for a post or page, kept only when the text backs it."""
    if is_free and "free" not in text.lower():
        is_free = None
    if is_free and (price_max or 0) > 0:
        # A paid price next to a free line ("toddlers free") does not make the whole thing free
        is_free = None
    if is_free is False and price_min is None and price_max is None and "$" not in text:
        is_free = None
    return is_free


def page_price_free(out: dict, text: str) -> dict:
    """The model's price reading of a ticket page, checked against free-entry wording.
    Returns out with is_free, price_min, price_max and price_text adjusted."""
    if not FREE_ENTRY.search(text) or (out["price_max"] or 0) > 0:
        # A paid price next to a free line ("Toddlers free") does not make the whole thing free
        out["is_free"] = None
        if not out["price_min"] and not out["price_max"]:
            # $0 with no free-entry wording is the model reading "free donuts" as the price
            out["price_min"] = out["price_max"] = out["price_text"] = None
    return out


def site_is_free(is_free, text: str) -> bool | None:
    """The model's is_free for a venue site: True only when the pages say free or no cover."""
    if is_free is not True or not re.search(r"free|no cover", text, re.I):
        return None
    return True
