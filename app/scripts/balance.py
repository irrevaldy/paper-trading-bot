import hashlib
import hmac
import os
import time
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("INDODAX_API_KEY", "")
secret = os.getenv("INDODAX_API_SECRET", "")

if not key or not secret:
    print("ERROR: INDODAX_API_KEY and INDODAX_API_SECRET not set in .env")
    exit(1)


def _tapi(method: str) -> dict:
    nonce = int(time.time() * 1000)
    params = {"method": method, "timestamp": nonce, "nonce": nonce}
    body = urlencode(params)
    sign = hmac.new(secret.encode(), body.encode(), hashlib.sha512).hexdigest()
    resp = requests.post(
        "https://indodax.com/tapi",
        data=body,
        headers={
            "Key": key,
            "Sign": sign,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("success") != 1:
        raise RuntimeError(data.get("error", data))
    return data["return"]


def _get_price_idr(asset: str) -> float | None:
    if asset == "idr":
        return 1.0
    pair = f"{asset}idr"
    try:
        resp = requests.get(f"https://indodax.com/api/ticker/{pair}", timeout=5)
        resp.raise_for_status()
        return float(resp.json()["ticker"]["last"])
    except Exception:
        return None


# ── Fetch balances ──────────────────────────────────────────────────────────
result = _tapi("getInfo")
balances = {k: float(v) for k, v in result["balance"].items() if float(v) > 0}

# ── Fetch current prices in IDR ─────────────────────────────────────────────
prices: dict[str, float] = {}
for asset in balances:
    price = _get_price_idr(asset)
    if price is not None:
        prices[asset] = price

# ── Print ───────────────────────────────────────────────────────────────────
print(f"\n{'ASSET':<10} {'BALANCE':>18} {'PRICE (IDR)':>20} {'VALUE (IDR)':>20}")
print("─" * 72)

total_idr = 0.0
for asset in sorted(balances):
    amount = balances[asset]
    price = prices.get(asset)
    if price is not None:
        value = amount * price
        total_idr += value
        print(
            f"{asset.upper():<10} {amount:>18.8f} {price:>20,.0f} {value:>20,.0f}"
        )
    else:
        print(f"{asset.upper():<10} {amount:>18.8f} {'n/a':>20} {'n/a':>20}")

print("─" * 72)
print(f"{'TOTAL':>50} {total_idr:>20,.0f}")
print()
