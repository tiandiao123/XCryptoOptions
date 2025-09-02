import os 

def option_margin(option_type: str,
                  spot_price: float,
                  strike: float,
                  mark_price: float,
                  contracts: int,
                  multiplier: float = 0.01,
                  margin_factor: float = 1.0):
    """
    计算期权卖方的初始保证金 (IMR) 和维持保证金 (MMR)
    支持 Call 和 Put
    
    Parameters
    ----------
    option_type : str
        "call" 或 "put"
    spot_price : float
        标的价格 (Index/Futures price)
    strike : float
        期权行权价
    mark_price : float
        期权标记价格 (单位 BTC)
    contracts : int
        卖出的合约张数
    multiplier : float
        每张合约乘数 (BTC/张)，OKX 通常是 0.01
    margin_factor : float
        保证金系数（Position Tier 不同会 >1），默认 1.0
    
    Returns
    -------
    (IMR, MMR)
        - IMR: 初始保证金 (BTC)
        - MMR: 维持保证金 (BTC)
    """
    
    # 计算 OTM Value
    if option_type.lower() == "call":
        otm_value = max(0.0, strike - spot_price)
    elif option_type.lower() == "put":
        otm_value = max(0.0, spot_price - strike)
    else:
        raise ValueError("option_type 必须是 'call' 或 'put'")
    
    # 转换成 BTC
    otm_value_btc = otm_value / spot_price if spot_price > 0 else 0.0
    
    # --- 初始保证金 IMR ---
    if option_type.lower() == "call":
        imr_per_contract = (max(0.1, 0.15 - otm_value / spot_price) * margin_factor + mark_price) * multiplier
    else:  # put
        imr_per_contract = (max(0.1 * (1 + mark_price), 0.15 - otm_value / spot_price) * margin_factor + mark_price) * multiplier
    
    IMR = imr_per_contract * contracts
    
    # --- 维持保证金 MMR ---
    if option_type.lower() == "call":
        mmr_per_contract = (0.075 * margin_factor + mark_price) * multiplier
    else:  # put
        mmr_per_contract = (0.075 * (1 + mark_price) * margin_factor + mark_price) * multiplier
    
    MMR = mmr_per_contract * contracts
    
    return IMR, MMR
