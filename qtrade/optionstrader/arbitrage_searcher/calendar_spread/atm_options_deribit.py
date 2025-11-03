import yaml
import numpy as np
from datetime import datetime
from typing import List, Dict, Any
from qtrade.optionstrader.arbitrage_searcher.option_data import OptionData
from qtrade.order_api.deribit.options_orderbook import (
    get_index_price,
    list_live_options,
    _get,
    DERIBIT_BASE
)


def get_atm_options(config: Dict[str, Any], currency: str = "BTC", env: str = "testnet") -> List[OptionData]:
    """
    获取ATM期权数据，包含希腊字母
    
    Args:
        config: 配置字典
        currency: 币种 (BTC/ETH)
        env: 环境 (testnet/mainnet)
        
    Returns:
        ATM期权数据列表
    """
    print(f"🔍 获取{currency} ATM期权数据...")
    
    try:
        # 1. 获取现货价格
        spot_price = get_index_price(currency, env)
        print(f"💰 {currency}现货价格: ${spot_price:,.2f}")
        
        # 2. 获取所有期权合约
        instruments = list_live_options(currency, env)
        print(f"📊 找到{len(instruments)}个期权合约")
        
        # 3. 向量化快速筛选ATM期权
        atm_tolerance = config["strike_criteria"]["atm_tolerance_pct"]
        
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
        
        print(f"✅ 向量化筛选完成: {len(atm_candidates)}个ATM候选期权 (从{len(instruments)}个中筛选, 用时<1ms)")
        
        # 4. 对筛选后的期权获取详细市场数据
        atm_options = []
        
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
                
                if days_to_expiry <= 3:
                    continue
                
                # 获取市场数据和希腊字母
                market_data = get_option_market_data(symbol, env)
                
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
                    atm_options.append(option_data)
                        
            except Exception as e:
                print(f"⚠️ 处理期权{instrument.get('instrument_name', 'Unknown')}时出错: {e}")
                continue
        
        print(f"✅ 筛选出{len(atm_options)}个有效ATM期权")
        return atm_options
        
    except Exception as e:
        print(f"❌ 获取ATM期权失败: {e}")
        return []


def get_option_market_data(symbol: str, env: str = "testnet") -> Dict[str, Any]:
    """
    获取期权的市场数据和希腊字母
    
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


        
        # 解析订单簿 - 直接从orderbook获取所有数据
        best_bid = orderbook.get("best_bid_price", 0)
        best_ask = orderbook.get("best_ask_price", 0)
        mid_price = (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0
        
        # 解析希腊字母 - 直接从orderbook获取
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



# 测试函数
def test_get_atm_options():
    """测试获取ATM期权功能"""
    
    # 加载配置
    config_path = "/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # 获取ATM期权
    atm_options = get_atm_options(config, "BTC", "testnet")
    
    # 显示结果
    print(f"\n📊 ATM期权结果:")
    print("=" * 80)
    
    for i, option in enumerate(atm_options[:5]):  # 只显示前5个
        print(f"\n期权 {i+1}: {option.symbol}")
        print(f"  执行价: ${option.strike:,.0f} | 类型: {option.option_type} | 到期: {option.days_to_expiry}天")
        print(f"  价格: Bid={option.bid:.4f}, Ask={option.ask:.4f}, Mid={option.mid_price:.4f}")
        print(f"  IV: {option.iv:.1%}")
        print(f"  希腊字母: Δ={option.delta:.3f}, Net Δ={option.net_delta:.3f}, Γ={option.gamma:.3f}, Θ={option.theta:.3f}")


if __name__ == "__main__":
    test_get_atm_options()