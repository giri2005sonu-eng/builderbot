"""Cart check, step 1: pick WHO does it.

   robu.in and robocraze.com (the two shops most listings come from) -> TinyFish BROWSER: a cloud browser session that Playwright drives with a
       fixed, auditable script (open the product page, click Add to cart, open the cart, read it). No AI in the loop, so it is fast, repeatable
       and uses no agent steps. It can only do what the script does: it never types anything and never goes near checkout (enforced by the code).
   any other shop, or when the browser run fails -> TinyFish WEB AGENT (credits, capped steps), exactly as before.

Every result carries `method` ("browser" or "agent"), `steps` (each line says which of the two did it) and, after a fallback, `fallback_reason`.
The page-driving part (`drive`) takes any Playwright Page, so it is tested offline against fake shop pages with a local Chromium."""
import os, re, urllib.request
from urllib.parse import urlparse
from . import tf

SUPPORTED = ("robu.in", "robocraze.com")       # shops the browser script is written for
BROWSER_TIMEOUT_S = 150                         # whole browser run (session start is 10-30 s alone)
NO_FALLBACK = ("401", "402", "403", "unauthorized", "forbidden", "payment required", "quota", "429")   # key/credit problems: the agent would fail the same way
MONEY = re.compile(r"(?:₹|Rs\.?|INR)\s*([\d,]+(?:\.\d+)?)", re.I)
OUT = re.compile(r"out of stock|sold out|currently unavailable", re.I)
ADD_CSS = ("form.cart button.single_add_to_cart_button", "button.single_add_to_cart_button", "form.cart button[type=submit]",
            "form[action*='/cart/add'] button[type=submit]", "form[action*='/cart/add'] [type=submit]", "form[action*='/cart/add'] button[name='add']")
# Blocks that list OTHER products (related / upsell / grids). A button inside one adds a different product, so it is never clicked.
OTHER_PRODUCTS = ".related, .upsells, .up-sells, .cross-sells, .products, [class*='related'], [class*='recommend'], [class*='upsell']"
SUMMARY_CSS = (".summary", ".entry-summary", ".product-summary", ".product__info-container", ".product-info")   # the main product's own text block
ADD_TEXT = re.compile(r"^\s*add to (cart|bag|basket)\s*$", re.I)


class BrowserCartError(Exception):
    """The browser script could not finish (page changed, element missing, ...). The caller may fall back to the agent."""


def host_of(url):
    return (urlparse(url or "").netloc or "").lower().split(":")[0].removeprefix("www.")


def supported(url):
    """True only for the shop itself or a real subdomain (robu.in, m.robu.in), never for look-alikes such as notrobu.in or robu.in.evil.com."""
    h = host_of(url)
    return any(h == s or h.endswith("." + s) for s in SUPPORTED)


def route(url):
    return "browser" if supported(url) and (url or "").lower().startswith(("http://", "https://")) else "agent"


def label(method):
    return {"browser": "TinyFish Browser", "agent": "TinyFish Web Agent"}.get(method, str(method))


def icon(method):
    return {"browser": "🌐", "agent": "🤖"}.get(method, "•")


def _money(text):
    out = []
    for m in MONEY.findall(text or ""):
        try: out.append(float(m.replace(",", "")))
        except ValueError: pass
    return out


def _tokens(name):
    return [t for t in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(t) >= 3][:6]


def _in_other_products(loc):
    """True if this element sits inside a related / upsell / product-grid block."""
    try: return bool(loc.evaluate("(e, sel) => !!e.closest(sel)", OTHER_PRODUCTS))
    except Exception: return False


def _add_button(page):
    """The Add to cart button of the MAIN product, or None. Buttons that belong to related products are skipped: clicking one would
    put a different product in the cart (that is how an out-of-stock page used to produce a misleading result)."""
    for loc in [page.locator(css) for css in ADD_CSS] + [page.get_by_role("button", name=ADD_TEXT)]:
        for i in range(min(loc.count(), 8)):
            if not _in_other_products(loc.nth(i)): return loc.nth(i)
    return None


def _out_of_stock(page, btn, body):
    """True only when the MAIN product is shown as out of stock; None when the page does not say (never a guess from other products' labels)."""
    flags = page.locator(".stock.out-of-stock, p.out-of-stock")
    for i in range(min(flags.count(), 5)):
        if not _in_other_products(flags.nth(i)): return True
    if btn is not None:
        try:
            if not btn.is_enabled() and OUT.search((btn.inner_text() or "") + " " + (btn.get_attribute("value") or "")): return True
        except Exception: pass
    if page.locator(OTHER_PRODUCTS).count() == 0:
        return True if OUT.search(body) else None
    for css in SUMMARY_CSS:
        loc = page.locator(css)
        if loc.count():
            return True if OUT.search(loc.first.inner_text()) else None
    return None


def _cart_row_text(page, tokens):
    """Text of the cart row that mentions the product, or '' (the first two name tokens must appear)."""
    need = tokens[:2]
    rows = page.locator("tr, li, .cart-item, .cart__row, [class*='cart-item'], [class*='cart_item']")
    for i in range(min(rows.count(), 40)):
        t = rows.nth(i).inner_text()
        low = t.lower()
        if need and all(w in low for w in need) and _money(t): return t
    return ""


def drive(page, url, steps):
    """The fixed script. `steps` collects {actor, text}. Returns the same dict shape the Web Agent returns in `result`."""
    def step(text): steps.append(dict(actor="browser", text=text))
    page.set_default_timeout(25000)
    origin = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    page.goto(url, wait_until="domcontentloaded"); step(f"Opened the product page on {host_of(url)}")
    h1 = page.locator("h1")
    name = (h1.first.inner_text().strip() if h1.count() else "")[:120]
    body = page.inner_text("body")
    btn = _add_button(page)
    if btn is None or not btn.is_enabled():
        out = _out_of_stock(page, btn, body)
        step("No usable Add to cart button for the main product" + (" (its page says out of stock)" if out else " (it may need a variant choice)"))
        return dict(product_name=name, in_stock=False if out else None, added_to_cart=False)
    btn.click(); step("Clicked Add to cart (one unit)")
    page.wait_for_timeout(2500)
    page.goto(origin + "/cart", wait_until="domcontentloaded"); step("Opened the cart page")
    page.wait_for_timeout(1500)
    cart = page.inner_text("body"); tokens = _tokens(name)
    row = _cart_row_text(page, tokens)
    if not row and not (tokens and sum(t in cart.lower() for t in tokens) >= max(1, len(tokens) * 2 // 3)):
        step("The product did not appear in the cart")
        return dict(product_name=name, in_stock=None, added_to_cart=False)
    amounts = _money(row)
    totals = re.findall(r"(?:grand\s+total|order\s+total|subtotal|total)\W{0,25}(?:₹|Rs\.?|INR)?\s*([\d,]+(?:\.\d+)?)", cart, re.I)
    step("Read the item price and cart total from the cart")
    res = dict(product_name=name, in_stock=True, added_to_cart=True)
    if amounts: res["unit_price_inr"] = amounts[0]
    if totals:
        try: res["cart_total_inr"] = float(totals[-1].replace(",", ""))
        except ValueError: pass
    return res


def _end_session(session_id):
    """Explicitly close the cloud browser (the SDK has no delete call; the REST endpoint does). Failures are ignored: sessions also expire by themselves."""
    try:
        req = urllib.request.Request(f"https://api.browser.tinyfish.ai/{session_id}", method="DELETE", headers={"X-API-Key": os.getenv("TINYFISH_API_KEY", "")})
        urllib.request.urlopen(req, timeout=15).close()
    except Exception:
        pass


def run_browser(url, timeout=None):
    """One cart check in a TinyFish cloud browser. Raises on any failure (BrowserCartError, TimeoutError, missing Playwright, ...)."""
    steps = []

    def job():
        try: from playwright.sync_api import sync_playwright
        except ImportError as e: raise BrowserCartError("Playwright is not installed (pip install playwright)") from e
        session = tf._client().browser.sessions.create(url=url)
        steps.append(dict(actor="browser", text="Started a TinyFish cloud browser session"))
        try:
            with sync_playwright() as p:
                browser = p.chromium.connect_over_cdp(session.cdp_url)
                try:
                    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                    page = ctx.pages[0] if ctx.pages else ctx.new_page()
                    result = drive(page, url, steps)
                finally:
                    try: browser.close()
                    except Exception: pass
        finally:
            _end_session(session.session_id)
            steps.append(dict(actor="browser", text="Closed the browser session"))
        return result

    result = tf.with_timeout(job, timeout or BROWSER_TIMEOUT_S, "TinyFish Browser")
    return dict(status="COMPLETED", result=result, num_of_steps=len(steps), method="browser", steps=steps)


def _agent_result(res, note):
    """Wrap a Web Agent answer in the same shape, with one honest step line saying the agent did it."""
    n = res.get("num_of_steps", "n/a") if isinstance(res, dict) else "n/a"
    out = dict(res or {}, method="agent")
    out["steps"] = [dict(actor="agent", text=f"The Web Agent opened the listing, added one unit and read the cart ({n} agent steps)")]
    out["route_note"] = note
    return out


def check(url, agent, use_cache=True):
    """Dispatcher. `agent(url)` runs the Web Agent. Browser first for robu.in / robocraze.com, agent for everything else and after a browser failure.
    Never raises for a failed browser run (it falls back); an agent error propagates to the caller."""
    if route(url) == "agent":
        return _agent_result(agent(url), f"{host_of(url) or 'This shop'} is not robu.in or robocraze.com, so the Web Agent does the cart check.")
    key = f"b:{url}"
    hit = tf.cache_get(key) if use_cache else None
    if hit: return dict(hit, cached=True)
    try:
        res = run_browser(url)
    except Exception as e:
        reason = str(e)[:160] or e.__class__.__name__
        if any(w in reason.lower() for w in NO_FALLBACK):
            raise RuntimeError(f"TinyFish Browser refused the request ({reason}). Check TINYFISH_API_KEY and your credits.") from e
        out = _agent_result(agent(url), f"The browser run failed ({reason}), so the Web Agent did the cart check instead.")
        out["fallback_reason"] = reason
        out["steps"] = [dict(actor="browser", text=f"The browser run failed: {reason}")] + out["steps"]
        return out
    r = res["result"]
    if r.get("added_to_cart") is False and r.get("in_stock") is not False:
        reason = "the browser script could not add the item to the cart"
        out = _agent_result(agent(url), f"The browser could not add the item ({reason}), so the Web Agent tried instead.")
        out["fallback_reason"] = reason
        out["steps"] = res["steps"] + out["steps"]
        return out
    if r.get("added_to_cart") and isinstance(r.get("unit_price_inr"), (int, float)): tf.cache_set(key, res)
    return dict(res, route_note=f"{host_of(url)} is one of the two shops handled by the TinyFish Browser.")
