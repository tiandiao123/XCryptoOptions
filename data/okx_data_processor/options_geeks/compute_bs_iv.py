import math
from datetime import datetime, timezone

# ---------- 基础正态函数 ----------
def _phi(x):  # 标准正态密度
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)

def _N(x):    # 标准正态分布函数（erf混合实现）
    """标准正态分布累积分布函数"""
    try:
        # 优先使用内置的高精度erf
        return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
    except (AttributeError, ImportError):
        # Fallback：自定义erf实现
        return _N_fallback(x)

def _N_fallback(x):
    """备用的A&S近似实现"""
    # 你的原始实现
    t = 1.0 / (1.0 + 0.2316419 * abs(x))
    a1, a2, a3, a4, a5 = 0.319381530, -0.356563782, 1.781477937, -1.821255978, 1.330274429
    poly = (((a5*t + a4)*t + a3)*t + a2)*t + a1
    nd = 1.0 - _phi(x) * poly
    return nd if x >= 0 else 1.0 - nd

# ---------- Black–Scholes（美元口径） ----------
def bs_price_usd(S, K, T, r, q, sigma, opt_type):
    if sigma <= 0 or T <= 0:
        # 退化：T→0 或 sigma→0，用内在价值近似
        if opt_type.lower().startswith('c'):
            return max(0.0, math.exp(-q*T)*S - math.exp(-r*T)*K)
        else:
            return max(0.0, math.exp(-r*T)*K - math.exp(-q*T)*S)

    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type.lower().startswith('c'):
        return math.exp(-q*T) * S * _N(d1) - math.exp(-r*T) * K * _N(d2)
    else:
        return math.exp(-r*T) * K * _N(-d2) - math.exp(-q*T) * S * _N(-d1)

def bs_price_coin(S, K, T, r, q, sigma, opt_type):
    # 币口径价格 = 美元口径价格 / S
    return bs_price_usd(S, K, T, r, q, sigma, opt_type) / S

# ---------- Black–76（用于期货为标的的情况，可选） ----------
def black76_price_usd(F, K, T, DF, sigma, opt_type):
    # DF = exp(-rT)；若给 r，则 DF = exp(-r*T)
    if sigma <= 0 or T <= 0:
        if opt_type.lower().startswith('c'):
            return max(0.0, DF * (F - K))
        else:
            return max(0.0, DF * (K - F))
    d1 = (math.log(F / K) + 0.5 * sigma * sigma * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if opt_type.lower().startswith('c'):
        return DF * (F * _N(d1) - K * _N(d2))
    else:
        return DF * (K * _N(-d2) - F * _N(-d1))

def black76_price_coin(F, K, T, DF, S, sigma, opt_type):
    # 币口径价格 = 美元口径价格 / S
    return black76_price_usd(F, K, T, DF, sigma, opt_type) / S

# ---------- 隐含波动率：稳健二分法 ----------
def implied_vol_from_coin_price(price_coin, opt_type,
                                S=None, K=None, T=None, r=0.0, q=0.0,
                                model="bs",
                                F=None, DF=None,
                                vol_lower=1e-6, vol_upper=5.0, tol=1e-8, max_iter=400):
    """
    反推 IV（返回年化波动率，单位=小数，比如 0.35=35%）
    - 币本位价格: price_coin（单位：BTC/ETH 等）
    - model="bs": 传 S,K,T,r,q
    - model="black76": 传 F, K, T, DF, 以及当前 S(用于从美元口径除回币口径)
    """
    if model.lower() == "bs":
        assert S is not None and K is not None and T is not None
        px = lambda sig: bs_price_coin(S, K, T, r, q, sig, opt_type)
    elif model.lower() in ("black76", "b76"):
        assert F is not None and K is not None and T is not None and DF is not None and S is not None
        px = lambda sig: black76_price_coin(F, K, T, DF, S, sig, opt_type)
    else:
        raise ValueError("model must be 'bs' or 'black76'")

    # 检查可解性（单调区间）
    f_low = px(vol_lower) - price_coin
    f_high = px(vol_upper) - price_coin
    if f_low * f_high > 0:
        # 价格超出了模型可达范围：返回边界或报错
        # 这里返回更接近的一端，实务中也可以抛异常让上层处理
        return vol_lower if abs(f_low) < abs(f_high) else vol_upper

    lo, hi = vol_lower, vol_upper
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = px(mid) - price_coin
        if abs(f_mid) < tol or (hi - lo) < tol:
            return max(mid, 0.0)
        # 二分
        if f_low * f_mid <= 0:
            hi = mid
            f_high = f_mid
        else:
            lo = mid
            f_low = f_mid
    return 0.5 * (lo + hi)  # 容错返回

# ---------- 辅助：按 Actual/365 计算年化 T ----------
def yearfrac_actual_365(d0, d1):
    if isinstance(d0, str):
        d0 = datetime.fromisoformat(d0.replace('Z','')).replace(tzinfo=timezone.utc)
    if isinstance(d1, str):
        d1 = datetime.fromisoformat(d1.replace('Z','')).replace(tzinfo=timezone.utc)
    days = (d1 - d0).days + (d1 - d0).seconds/86400.0
    return max(days, 0.0) / 365.0



def yearfrac_now_to_expiry(expiry_utc, basis="ACT/365"):
    """
    expiry_utc: datetime(…, tzinfo=timezone.utc) 或 ISO 字符串（带 Z）
    basis: "ACT/365", "ACT/365F", or "ACT/252"
    """ 
    if isinstance(expiry_utc, str):
        if expiry_utc.endswith('Z'):
            expiry_utc = expiry_utc[:-1]
        expiry_utc = datetime.fromisoformat(expiry_utc).replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    print(now)
    sec = (expiry_utc - now).total_seconds()
    if sec <= 0:
        return 0.0

    days = sec / 86400.0
    if basis.upper() in ("ACT/365", "ACT/365F"):
        return days / 365.0
    elif basis.upper() == "ACT/252":
        return days / 252.0
    else:
        raise ValueError("Unknown basis")

def bs_delta(S, K, T, r, q, sigma, is_call=True):
    """
    计算Black-Scholes Delta
    Delta = ∂C/∂S (期权价格对标的价格的敏感度)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    d1 = (math.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    
    if is_call:
        return math.exp(-q*T) * _N(d1)      # 看涨期权
    else:
        return math.exp(-q*T) * (_N(d1) - 1.0)  # 看跌期权 = N(d1) - 1

def calculate_pa_delta(S, K, T, r, sigma, option_price_btc, is_call=True):
    """
    PA Delta = BS Delta - 期权价格(BTC单位)
    
    衡量：当BTC价格变化1%时，期权价格变化多少BTC
    """
    bs_delta_value = bs_delta(S, K, T, r, 0.0, sigma, is_call) # OKX假设无分红
    pa_delta = bs_delta_value - option_price_btc
    return pa_delta


def bs_gamma(S, K, T, r, q, sigma):
    """
    计算Black-Scholes Gamma
    Gamma = ∂²C/∂S² = ∂Delta/∂S
    
    对于看涨和看跌期权，Gamma是相同的
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    d1 = (math.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    
    # Gamma = φ(d1) * exp(-qT) / (S * σ * √T)
    gamma = _phi(d1) * math.exp(-q*T) / (S * sigma * math.sqrt(T))
    
    return gamma

def pa_gamma(S, K, T, r, q, sigma, option_price_coin, is_call=True):
    """
    计算PA Gamma
    基于公式: Γ_PA = S × Γ_BS - Δ_PA
    """
    # 计算BS Gamma
    gamma_bs = bs_gamma(S, K, T, r, q, sigma)
    
    # 计算PA Delta
    delta_pa = calculate_pa_delta(S, K, T, r, sigma, option_price_coin, is_call)
    
    # PA Gamma = S × BS Gamma - PA Delta
    gamma_pa = S * gamma_bs - delta_pa
    
    return gamma_pa


def bs_vega(S, K, T, r, q, sigma):
    """
    计算Black-Scholes Vega
    Vega = ∂V/∂σ (期权价格对波动率的敏感度)
    
    对于看涨和看跌期权，Vega是相同的
    
    Parameters:
    -----------
    S : float
        现货价格
    K : float
        执行价格
    T : float
        到期时间(年)
    r : float
        无风险利率
    q : float
        分红率
    sigma : float
        隐含波动率
        
    Returns:
    --------
    float
        Vega值 (期权价格对1%波动率变化的敏感度，单位：USD)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    d1 = (math.log(S/K) + (r - q + 0.5*sigma**2)*T) / (sigma*math.sqrt(T))
    
    # Vega = S * φ(d1) * √T * exp(-qT) / 100
    # 除以100是因为Vega通常表示对1%波动率变化的敏感度
    vega = S * _phi(d1) * math.sqrt(T) * math.exp(-q*T) / 100.0
    
    return vega


def pa_vega(S, K, T, r, q, sigma, option_price_coin, is_call=True):
    """
    计算PA Vega (币本位调整的Vega)
    
    对于币本位期权，PA Vega是币本位价格对波动率的敏感度
    由于 V_coin = V_USD / S，所以 PA_Vega = BS_Vega / S
    
    Parameters:
    -----------
    S : float
        现货价格
    K : float
        执行价格  
    T : float
        到期时间(年)
    r : float
        无风险利率
    q : float
        分红率
    sigma : float
        隐含波动率
    option_price_coin : float
        期权价格(币本位) - 这里保留参数为了兼容性
    is_call : bool
        是否为看涨期权
        
    Returns:
    --------
    float
        PA Vega值 (期权币本位价格对1%波动率变化的敏感度，单位：BTC)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    
    # 计算BS Vega (单位：USD)
    vega_bs = bs_vega(S, K, T, r, q, sigma)
    
    # PA Vega = BS Vega / S (单位：BTC)
    # 这是币本位价格对波动率的直接敏感度
    vega_pa = vega_bs / S
    
    return vega_pa


if __name__ == "__main__":
    # print("=== Black-Scholes 计算函数测试 ===")
    # print("使用示例数据进行计算...")
    
    # expiry = "2025-09-05T08:00:00Z"   # 按合约规格的UTC到期时刻
    # T = yearfrac_now_to_expiry(expiry, basis="ACT/365")  # 或 ACT/365F / ACT/252
    # print(f"到期时间: {T:.4f} 年")
    
    S = 35000
    K = 34968.5
    price_coin = 0.059
    opt_type = 'c'
    
    r = 0.013

    T = 0.00873

    iv = implied_vol_from_coin_price(price_coin, opt_type,
                                    S=S, K=K, T=T, r=r, q=0.0,
                                    model="bs")
    print(f"隐含波动率 IV: {iv:.4f} ({iv:.2%})")
    
    # get bs delta and pa delta
    if opt_type == 'c':
        is_call = True
    else:
        is_call = False
        
    bs_delta_value = bs_delta(S, K, T, r, 0.0, iv, is_call=is_call)
    pa_delta_value = calculate_pa_delta(S, K, T, r, iv, price_coin, is_call=is_call)
    print(f"BS Delta: {bs_delta_value:.4f}, PA Delta: {pa_delta_value:.4f}")
    
    # get pa gamma and bs gamma
    bs_gamma_value = bs_gamma(S, K, T, r, 0.0, iv)
    pa_gamma_value = pa_gamma(S, K, T, r, 0.0, iv, price_coin, is_call=is_call)
    print(f"BS Gamma: {bs_gamma_value:.6f}, PA Gamma: {pa_gamma_value:.6f}")
    
    # get bs vega and pa vega
    bs_vega_value = bs_vega(S, K, T, r, 0.0, iv)
    pa_vega_value = pa_vega(S, K, T, r, 0.0, iv, price_coin, is_call=is_call)
    print(f"BS Vega: {bs_vega_value:.4f}, PA Vega: {pa_vega_value:.4f}")
    
    print("\n" + "="*50)
    print("💡 要使用实时期权数据进行计算，请运行:")
    print("   python real_time_option_calculator.py")
    print("或者:")
    print("   python option_calculator_demo.py \"BTC-USD-250912-114000-C\"")
    print("="*50)
    
    
    


