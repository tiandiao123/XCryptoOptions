import re
import pandas as pd
import numpy as np

_EXP_RE = re.compile(r'-(\d{6})-')   # 匹配 yymmdd

def compute_ttm_okx(df, symbol_col="symbol", time_col="time",
                    day_count="ACT/365", clip_zero=True):
    """
    依据 OKX 期权规则（到期日 08:00 UTC）计算每行的年化到期时间 T。
    - df[symbol_col]: 形如 BTC-USD-210115-35000-C
    - df[time_col]: 时间戳（可以是字符串，带或不带 ' UTC'）
    - day_count: 'ACT/365' 或 'ACT/365.25'
    """
    # 1) 解析到期日（yymmdd）→ 到期时刻（08:00 UTC）
    def _expiry_dt(symbol):
        m = _EXP_RE.search(symbol)
        if not m:
            return pd.NaT
        yymmdd = m.group(1)
        yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
        yyyy = 2000 + yy  # 假设 20xx
        # 到期时刻固定 08:00:00 UTC
        return pd.Timestamp(year=yyyy, month=mm, day=dd, hour=8, tz="UTC")

    expiry = df[symbol_col].map(_expiry_dt)

    # 2) 规范化观测时间为 tz-aware UTC
    t = df[time_col].astype(str).str.replace(" UTC", "", regex=False)
    t = pd.to_datetime(t, utc=True, errors="coerce")

    # 3) 计算实际天数差
    seconds = (expiry - t).dt.total_seconds()

    # 4) 年化（day count）
    if day_count.upper() == "ACT/365.25":
        year_sec = 365.25 * 24 * 3600.0
    else:  # 默认 ACT/365
        year_sec = 365.0 * 24 * 3600.0

    T = seconds / year_sec

    if clip_zero:
        T = np.clip(T, 0.0, None)

    return T

# 用法示例
data = pd.read_csv("/home/ubuntu/options_trading/data.csv")  # 你的 DataFrame
data["T_years"] = compute_ttm_okx(data, symbol_col="symbol", time_col="time")
# 看看结果
print(data[["symbol", "time", "T_years"]].head())


data.to_csv("data_with_ttm.csv")
