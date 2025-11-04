import requests
import datetime as dt

OKX_BASE = "https://www.okx.com"

def get_option_greeks_official(inst_id: str) -> dict:
    """
    从 OKX 官方 REST 接口 /api/v5/public/opt-summary 拿到单个期权合约的希腊字母。
    inst_id 例：'ETH-USD-251114-3400-C' 或 'BTC-USD-251114-34000-P'
    返回：包含 deltaBS/deltaPA/gammaBS/gammaPA/thetaBS/thetaPA/vegaBS/vegaPA/markVol/markPx/idxPx 等字段
    """
    parts = inst_id.split("-")
    if len(parts) < 5:
        raise ValueError(f"instId 格式不对：{inst_id}")
    uly = f"{parts[0]}-{parts[1]}"   # 'ETH-USD' / 'BTC-USD'

    url = f"{OKX_BASE}/api/v5/public/opt-summary"
    # 按“标的指数”取整条期权链（官方要求传 uly 或 instFamily，REST 这边传 uly 即可）
    r = requests.get(url, params={"uly": uly}, timeout=15)
    r.raise_for_status()
    rows = r.json().get("data", []) or []

    # 精确匹配 instId
    row = next((it for it in rows if it.get("instId") == inst_id), None)
    if not row:
        # 给出同到期或同方向的若干候选，方便你检查行权价或位数
        exp6 = parts[2]
        cp = parts[4].upper()
        candidates = [it["instId"] for it in rows
                      if it.get("instId","").split("-")[2] == exp6
                      and it.get("instId","").split("-")[4].upper() == cp][:20]
        raise RuntimeError(f"opt-summary 未找到 {inst_id}，检查到期日/行权价是否写对。"
                           f" 同到期同方向示例：{candidates}")

    # # 官方返回里就含有希腊字段
    # keys = [
    #     "deltaBS","deltaPA","gammaBS","gammaPA","thetaBS","thetaPA","vegaBS","vegaPA",
    #     "markVol","markPx","last","askPx","bidPx","idxPx","underlying","instId"
    # ]
    # return {k: row.get(k) for k in keys if k in row}

    return row 

# ——— 用法示例 ———
if __name__ == "__main__":
    print(get_option_greeks_official("ETH-USD-251114-3400-C"))
    # print(get_option_greeks_official("BTC-USD-251114-34000-C"))
