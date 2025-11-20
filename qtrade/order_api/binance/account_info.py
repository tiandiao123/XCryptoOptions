import hmac
import hashlib
import time
import urllib.parse
from typing import Any, Dict, Optional, List

import requests

SPOT_BASE = "https://api.binance.com"
FUTURES_BASE = "https://fapi.binance.com"


class BinanceAccountClient:
    def __init__(self, api_key: str, api_secret: str, recv_window: int = 5000, timeout: int = 15):
        self.api_key = api_key
        self.api_secret = api_secret.encode()
        self.recv_window = recv_window
        self.timeout = timeout

    def _sign(self, query: str) -> str:
        return hmac.new(self.api_secret, query.encode(), hashlib.sha256).hexdigest()

    def _headers(self) -> Dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def _request(self, base: str, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False):
        url = f"{base}{path}"
        params = dict(params or {})
        if signed:
            params.setdefault("timestamp", int(time.time() * 1000))
            params.setdefault("recvWindow", self.recv_window)
            query = urllib.parse.urlencode(params, doseq=True)
            params["signature"] = self._sign(query)
        if method.upper() == "GET":
            r = requests.get(url, headers=self._headers() if signed else None, params=params, timeout=self.timeout)
        elif method.upper() == "POST":
            r = requests.post(url, headers=self._headers() if signed else None, params=params, timeout=self.timeout)
        else:
            raise ValueError(f"Unsupported method: {method}")
        r.raise_for_status()
        return r.json()

    # Spot account info
    def get_spot_account(self) -> Dict[str, Any]:
        return self._request(SPOT_BASE, "GET", "/api/v3/account", signed=True)

    def get_spot_balances(self) -> List[Dict[str, Any]]:
        acct = self.get_spot_account()
        return acct.get("balances", [])

    # Futures account info
    def get_futures_account(self) -> Dict[str, Any]:
        return self._request(FUTURES_BASE, "GET", "/fapi/v2/account", signed=True)

    def get_futures_balance(self) -> List[Dict[str, Any]]:
        return self._request(FUTURES_BASE, "GET", "/fapi/v2/balance", signed=True)

    def get_futures_positions(self) -> List[Dict[str, Any]]:
        # positionRisk includes positionAmt, entryPrice, liquidationPrice, unrealizedProfit, marginType, leverage, etc.
        return self._request(FUTURES_BASE, "GET", "/fapi/v2/positionRisk", signed=True)


def create_account_client(api_key: str, api_secret: str) -> BinanceAccountClient:
    return BinanceAccountClient(api_key=api_key, api_secret=api_secret)


if __name__ == "__main__":

    client = create_account_client(api_key="GC3B0Dg5ykdtSWrI5kn6LcU61e2750QGQFdjDl9i0jIZFxbAuor1kmnKJk9YtY8Y", 
                                    api_secret="")

    # Spot
    spot_acct = client.get_spot_account()
    print("Spot account:")
    print(spot_acct)

    # Futures
    futures_acct = client.get_futures_account()
    print("\nFutures account:")
    print(futures_acct)

    futures_bal = client.get_futures_balance()
    print("\nFutures balances:")
    print(futures_bal)

    futures_pos = client.get_futures_positions()
    print("\nFutures positions:")
    print(futures_pos)


