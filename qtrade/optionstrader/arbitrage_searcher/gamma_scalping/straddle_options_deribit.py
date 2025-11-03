"""
Gamma Scalping - ATM期权筛选器
专门为Selling Straddle策略筛选合适的ATM期权
独立实现，避免与calendar_spread参数混杂
"""

import yaml
import numpy as np
from typing import List, Dict, Any, Tuple
from datetime import datetime

# 只复用基础数据结构和API调用
from qtrade.optionstrader.arbitrage_searcher.option_data import OptionData
from qtrade.order_api.deribit.options_orderbook import (
    get_index_price,
    list_live_options,
    _get,
    DERIBIT_BASE
)


def get_straddle_atm_options(config: Dict[str, Any], currency: str = "BTC", env: str = "testnet") -> List[OptionData]:
    """
    获取适合Selling Straddle的ATM期权 - 独立实现
    
    Args:
        config: Selling Straddle配置字典
        currency: 币种 (BTC/ETH)
        env: 环境 (testnet/mainnet)
        
    Returns:
        筛选后的ATM期权列表
    """
    print(f"🔍 获取{currency} Selling Straddle ATM期权...")
    
    try:
        # 1. 获取现货价格
        spot_price = get_index_price(currency, env)
        print(f"💰 {currency}现货价格: ${spot_price:,.2f}")
        
        # 2. 获取所有期权合约
        instruments = list_live_options(currency, env)
        print(f"📊 找到{len(instruments)}个期权合约")
        
        # 3. 应用Selling Straddle特定的筛选条件
        straddle_options = _filter_straddle_options(instruments, spot_price, config, env)
        
        print(f"✅ Selling Straddle筛选后剩余 {len(straddle_options)} 个期权")
        
        return straddle_options
        
    except Exception as e:
        print(f"❌ 获取Selling Straddle ATM期权失败: {e}")
        return []


def _filter_straddle_options(instruments: List[Dict], spot_price: float, config: Dict[str, Any], env: str) -> List[OptionData]:
    """
    应用Selling Straddle特定的筛选条件 - 独立实现
    
    Args:
        instruments: 所有期权合约列表
        spot_price: 现货价格
        config: Selling Straddle配置字典
        env: 环境
        
    Returns:
        筛选后的期权列表
    """
    
    # 获取配置参数
    strike_criteria = config.get("strike_criteria", {})
    atm_tolerance = strike_criteria.get("atm_tolerance_pct", 0.01)  # 1%
    
    time_criteria = config.get("time_criteria", {})
    min_days = time_criteria.get("min_days_to_expiry", 7)
    max_days = time_criteria.get("max_days_to_expiry", 25)
    
    # 1. 向量化快速筛选ATM期权
    print(f"🚀 向量化筛选ATM期权 (容忍度: ±{atm_tolerance:.1%})...")
    
    # 提取所有执行价到numpy数组
    strikes = np.array([float(inst.get("strike", 0)) for inst in instruments])
    
    # 向量化计算ATM偏离度
    atm_deviations = np.abs(strikes - spot_price) / spot_price
    
    # 向量化筛选ATM期权
    atm_mask = atm_deviations <= atm_tolerance
    atm_indices = np.where(atm_mask)[0]
    
    # 快速提取ATM候选期权
    atm_candidates = [instruments[i] for i in atm_indices]
    
    print(f"✅ 向量化筛选完成: {len(atm_candidates)}个ATM候选期权 (从{len(instruments)}个中筛选)")
    
    # 2. 对筛选后的期权进行详细筛选
    straddle_options = []
    
    print(f"📡 获取{len(atm_candidates)}个期权的市场数据...")
    
    for instrument in atm_candidates:
        try:
            strike = float(instrument["strike"])
            expiry_ts = int(instrument["expiration_timestamp"])
            option_type = instrument["option_type"]  # "call" or "put"
            symbol = instrument["instrument_name"]
            
            # 计算到期天数
            expiry_dt = datetime.fromtimestamp(expiry_ts / 1000)
            days_to_expiry = (expiry_dt - datetime.now()).days
            
            # 时间筛选：7-25天期权
            if not (min_days <= days_to_expiry <= max_days):
                continue
            
            # 获取市场数据和希腊字母
            market_data = _get_straddle_option_market_data(symbol, env)
            
            if market_data:
                option_data = OptionData(
                    symbol=symbol,
                    strike=strike,
                    expiry=expiry_dt.strftime("%Y-%m-%d"),
                    days_to_expiry=days_to_expiry,
                    option_type=option_type.upper()[0],  # "C" or "P"
                    iv=market_data.get("mark_iv", 0),
                    bid=market_data.get("best_bid", 0),
                    ask=market_data.get("best_ask", 0),
                    mid_price=market_data.get("mid_price", 0),
                    delta=market_data.get("greeks", {}).get("delta", 0),
                    net_delta=market_data.get("greeks", {}).get("net_delta", 0),
                    gamma=market_data.get("greeks", {}).get("gamma", 0),
                    vega=market_data.get("greeks", {}).get("vega", 0),
                    theta=market_data.get("greeks", {}).get("theta", 0),
                    rho=market_data.get("greeks", {}).get("rho", 0),
                    open_interest=market_data.get("open_interest", 0)
                )
                
                # # 应用Selling Straddle特定的数据质量检查
                # if _is_valid_straddle_option(option_data, config):
                straddle_options.append(option_data)
                    
        except Exception as e:
            print(f"⚠️ 处理期权{instrument.get('instrument_name', 'Unknown')}时出错: {e}")
            continue
    
    return straddle_options


def _get_straddle_option_market_data(symbol: str, env: str = "testnet") -> Dict[str, Any]:
    """
    获取期权的市场数据和希腊字母 - 专用于Selling Straddle
    
    Args:
        symbol: 期权合约名称
        env: 环境
        
    Returns:
        包含价格和希腊字母的字典
    """
    try:
        base = DERIBIT_BASE[env]
        
        # 获取订单簿数据（包含希腊字母和所有市场数据）
        orderbook = _get(base, "public/get_order_book", {
            "instrument_name": symbol,
            "depth": 1
        })
        
        # 解析订单簿数据
        best_bid = orderbook.get("best_bid_price", 0)
        best_ask = orderbook.get("best_ask_price", 0)
        mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0
        
        # 解析希腊字母
        greeks_data = orderbook.get("greeks", {})
        raw_delta = greeks_data.get("delta", 0)
        
        # 计算Net Delta近似值：当前Delta - 中间价对应的隐含Delta
        # 这里用中间价作为市场隐含的Delta基准
        net_delta_approx = raw_delta - mid_price if mid_price > 0 else raw_delta
        
        greeks = {
            "delta": raw_delta,  # 保留原始Delta
            "net_delta": net_delta_approx,  # 添加Net Delta近似值
            "gamma": greeks_data.get("gamma", 0),
            "vega": greeks_data.get("vega", 0),
            "theta": greeks_data.get("theta", 0),
            "rho": greeks_data.get("rho", 0)
        }
        
        # IV数据 - 转换为小数形式
        mark_iv = orderbook.get("mark_iv", 0) / 100  # 34.12 -> 0.3412
        
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "mark_price": orderbook.get("mark_price", 0),
            "mark_iv": mark_iv,
            "open_interest": orderbook.get("open_interest", 0),
            "greeks": greeks
        }
        
    except Exception as e:
        print(f"⚠️ 获取{symbol}市场数据失败: {e}")
        return {}


def _is_valid_straddle_option(option: OptionData, config: Dict[str, Any]) -> bool:
    """
    检查期权是否适合Selling Straddle - 专用数据质量检查
    
    Args:
        option: 期权数据
        config: 配置字典
        
    Returns:
        是否有效
    """
    
    # 获取配置参数
    pairing_criteria = config.get("pairing_criteria", {})
    min_iv = pairing_criteria.get("min_iv", 0.01)
    max_iv = pairing_criteria.get("max_iv", 3.0)
    min_option_price = pairing_criteria.get("min_option_price", 0.0001)
    
    market_filters = config.get("market_filters", {})
    liquidity = market_filters.get("liquidity", {})
    price_sanity = market_filters.get("price_sanity", {})
    
    # 1. IV合理性检查
    if not (min_iv <= option.iv <= max_iv):
        return False
    
    # 2. 价格有效性检查
    if option.bid <= 0 or option.ask <= 0 or option.mid_price < min_option_price:
        return False
    
    # 3. 流动性检查
    if liquidity:
        min_bid = liquidity.get("min_bid_price", 0)
        max_spread_pct = liquidity.get("max_bid_ask_spread_pct", 1.0)
        min_oi = liquidity.get("min_open_interest", 0)
        
        if option.bid < min_bid:
            return False
        
        # 检查买卖价差
        if option.mid_price > 0:
            spread_pct = (option.ask - option.bid) / option.mid_price
            if spread_pct > max_spread_pct:
                return False
        
        if option.open_interest < min_oi:
            return False
    
    # 4. 价格合理性检查
    if price_sanity:
        min_total = price_sanity.get("min_total_premium", 0)
        max_total = price_sanity.get("max_total_premium", 1.0)
        
        # 单个期权价格应该在合理范围内
        if not (min_total/4 <= option.mid_price <= max_total/2):
            return False
    
    return True


def group_options_for_straddle(options: List[OptionData]) -> Dict[Tuple[float, int], Dict[str, List[OptionData]]]:
    """
    按执行价和到期天数分组期权，便于Straddle配对
    
    Args:
        options: 期权列表
        
    Returns:
        分组后的期权字典: {(strike, days_to_expiry): {"C": [calls], "P": [puts]}}
    """
    grouped = {}
    
    for option in options:
        # 使用执行价和到期天数作为分组键
        key = (option.strike, option.days_to_expiry)
        
        if key not in grouped:
            grouped[key] = {"C": [], "P": []}
        
        grouped[key][option.option_type].append(option)
    
    return grouped


def find_valid_straddle_pairs(grouped_options: Dict[Tuple[float, int], Dict[str, List[OptionData]]], 
                             config: Dict[str, Any]) -> List[Tuple[OptionData, OptionData]]:
    """
    从分组的期权中找到有效的Straddle配对（Call + Put）
    
    Args:
        grouped_options: 分组后的期权
        config: 配置字典
        
    Returns:
        有效的(Call, Put)配对列表
    """
    valid_pairs = []
    
    pairing_criteria = config.get("pairing_criteria", {})
    strike_tolerance = pairing_criteria.get("strike_match_tolerance", 0.005)
    
    for (strike, days), options_dict in grouped_options.items():
        calls = options_dict.get("C", [])
        puts = options_dict.get("P", [])
        
        if not calls or not puts:
            continue
        
        # 寻找最佳Call和Put配对
        for call in calls:
            for put in puts:
                # 检查执行价格匹配（应该已经相同，但加个容忍度检查）
                strike_diff = abs(call.strike - put.strike) / call.strike
                if strike_diff > strike_tolerance:
                    continue
                
                # 检查到期时间匹配（应该已经相同）
                if abs(call.days_to_expiry - put.days_to_expiry) > 1:
                    continue
                
                # 检查数据有效性
                if (call.iv > 0 and put.iv > 0 and 
                    call.mid_price > 0 and put.mid_price > 0):
                    valid_pairs.append((call, put))
    
    return valid_pairs


def load_straddle_config(config_path: str = None) -> Dict[str, Any]:
    """
    加载Selling Straddle配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    if config_path is None:
        config_path = "/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return get_default_straddle_config()


def get_default_straddle_config() -> Dict[str, Any]:
    """默认Selling Straddle配置"""
    return {
        "time_criteria": {
            "min_days_to_expiry": 7,
            "max_days_to_expiry": 25
        },
        "strike_criteria": {
            "atm_tolerance_pct": 0.01
        },
        "pairing_criteria": {
            "strike_match_tolerance": 0.005,
            "min_iv": 0.01,
            "max_iv": 3.0,
            "min_option_price": 0.0001
        },
        "market_filters": {
            "liquidity": {
                "min_bid_price": 0.001,
                "max_bid_ask_spread_pct": 0.25,
                "min_open_interest": 3
            }
        }
    }


if __name__ == "__main__":
    # 测试Selling Straddle ATM期权筛选
    print("🚀 测试Selling Straddle ATM期权筛选...")
    
    # 加载配置
    config = load_straddle_config()
    
    # 获取ATM期权
    straddle_options = get_straddle_atm_options(config, "BTC", "testnet")
    
    if straddle_options:
        print(f"\n✅ 找到 {len(straddle_options)} 个适合Selling Straddle的ATM期权:")
        
        # 按到期时间分组显示
        by_expiry = {}
        for opt in straddle_options:
            key = opt.days_to_expiry
            if key not in by_expiry:
                by_expiry[key] = []
            by_expiry[key].append(opt)
        
        for days in sorted(by_expiry.keys()):
            options = by_expiry[days]
            print(f"\n📅 {days}天到期 ({len(options)}个期权):")
            for opt in options[:3]:  # 只显示前3个
                print(f"   {opt}")
        
        # 测试分组和配对
        print(f"\n🔍 测试Straddle配对...")
        grouped = group_options_for_straddle(straddle_options)
        pairs = find_valid_straddle_pairs(grouped, config)
        
        print(f"✅ 找到 {len(pairs)} 个有效的Straddle配对")
        for i, (call, put) in enumerate(pairs, 1): 
            total_premium = call.mid_price + put.mid_price
            avg_iv = (call.iv + put.iv) / 2
            
            print(f"\n   📊 Straddle配对 #{i}:")
            print(f"      🔵 Call: {call.symbol}")
            print(f"         执行价: ${call.strike:,.0f} | 到期: {call.days_to_expiry}天 | IV: {call.iv:.1%}")
            print(f"         价格: Bid={call.bid:.4f}, Ask={call.ask:.4f}, Mid={call.mid_price:.4f}")
            print(f"         希腊字母: Δ={call.delta:.3f}, Net Δ={call.net_delta:.3f}, Γ={call.gamma:.3f}, Θ={call.theta:.3f}")
            
            print(f"      🔴 Put:  {put.symbol}")
            print(f"         执行价: ${put.strike:,.0f} | 到期: {put.days_to_expiry}天 | IV: {put.iv:.1%}")
            print(f"         价格: Bid={put.bid:.4f}, Ask={put.ask:.4f}, Mid={put.mid_price:.4f}")
            print(f"         希腊字母: Δ={put.delta:.3f}, Net Δ={put.net_delta:.3f}, Γ={put.gamma:.3f}, Θ={put.theta:.3f}")
            
            print(f"      💰 Straddle总览:")
            print(f"         总权利金: {total_premium:.4f} BTC")
            print(f"         平均IV: {avg_iv:.1%}")
            print(f"         净Delta: {call.delta + put.delta:.3f}")
            print(f"         净Net Delta: {call.net_delta + put.net_delta:.3f}")
            print(f"         总Gamma: {call.gamma + put.gamma:.3f}")
            print(f"         总Theta: {call.theta + put.theta:.3f}")
            print(f"         持仓量: Call={call.open_interest}, Put={put.open_interest}")
    else:
        print("❌ 未找到适合的期权")
