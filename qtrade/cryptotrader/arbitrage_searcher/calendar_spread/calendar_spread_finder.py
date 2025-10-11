import numpy as np
from typing import List, Dict, Any, Tuple
from dataclasses import dataclass

import yaml

# 导入ATM期权筛选器
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.atm_options_filter import (
    OptionData, 
    get_atm_options
)

@dataclass
class CalendarSpreadOpportunity:
    """Calendar Spread机会数据结构"""
    rank: int
    short_option: OptionData  # 卖出的短期期权
    long_option: OptionData   # 买入的长期期权
    iv_spread: float          # IV价差
    iv_spread_pct: float      # IV价差百分比
    time_gap_days: int        # 时间间隔（天）
    net_premium: float        # 净保险费（负数表示支出）
    max_profit_potential: float  # 最大盈利潜力
    signal_strength: str      # 信号强度：WEAK, MODERATE, STRONG

    open_status: bool = False  # 是否持仓
    contracts: float = 0.0 # 持仓大小


def update_calendar_spread_opportunity(opportunity: CalendarSpreadOpportunity,
                                       realized_vol: float,
                                       net_delta_only: bool = True,
                                       env: str = "testnet"):
    """
    更新Calendar Spread机会的实时Greeks数据
    
    Args:
        opportunity: 现有的CalendarSpreadOpportunity对象
        realized_vol: 最新的实现波动率
        net_delta_only: 如果为True，只返回combined net delta；如果为False，返回完整更新的对象
        env: 交易环境 ("testnet" 或 "mainnet")
    
    Returns:
        如果net_delta_only=True: float (combined net delta)
        如果net_delta_only=False: CalendarSpreadOpportunity (更新后的完整对象)
    """
    try:
        # 导入API函数
        from qtrade.order_api.deribit_order_placer.options_orderbook import _get, DERIBIT_BASE
        
        # 获取最新的期权市场数据
        def get_latest_option_data(symbol: str) -> Dict[str, Any]:
            """获取单个期权的最新市场数据"""
            try:
                base = DERIBIT_BASE[env]
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
                net_delta_approx = raw_delta - mid_price if mid_price > 0 else raw_delta
                
                return {
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "mid_price": mid_price,
                    "mark_price": orderbook.get("mark_price", 0),
                    "mark_iv": orderbook.get("mark_iv", 0) / 100,  # 转换为小数
                    "open_interest": orderbook.get("open_interest", 0),
                    "greeks": {
                        "delta": raw_delta,
                        "net_delta": net_delta_approx,
                        "gamma": greeks_data.get("gamma", 0),
                        "vega": greeks_data.get("vega", 0),
                        "theta": greeks_data.get("theta", 0),
                        "rho": greeks_data.get("rho", 0)
                    }
                }
            except Exception as e:
                print(f"⚠️ 获取{symbol}最新数据失败: {e}")
                return None
        
        # 获取Short和Long期权的最新数据
        short_data = get_latest_option_data(opportunity.short_option.symbol)
        long_data = get_latest_option_data(opportunity.long_option.symbol)
        
        if not short_data or not long_data:
            print("❌ 无法获取期权最新数据")
            if net_delta_only:
                # 返回原有的net delta (Calendar Spread的净Delta = Long Delta - Short Delta)
                original_net_delta = opportunity.long_option.net_delta - opportunity.short_option.net_delta
                return original_net_delta
            else:
                return opportunity  # 返回原对象
        
        # 如果只需要net delta，直接计算并返回
        if net_delta_only:
            short_net_delta = short_data["greeks"]["net_delta"]
            long_net_delta = long_data["greeks"]["net_delta"]
            # Calendar Spread Net Delta = 买入期权的Net Delta - 卖出期权的Net Delta
            # 因为我们买入长期期权(+Delta)，卖出短期期权(-Delta)
            combined_net_delta = long_net_delta - short_net_delta
            
            print(f"🔄 更新Calendar Spread Net Delta:")
            print(f"   Short (卖出): {short_net_delta:.4f}")
            print(f"   Long (买入): {long_net_delta:.4f}")
            print(f"   Combined: {combined_net_delta:.4f}")
            print(f"   对冲建议: {'做空标的' if combined_net_delta > 0 else '做多标的' if combined_net_delta < 0 else '无需对冲'}")
            return combined_net_delta
        
        # 如果需要完整更新，直接更新原对象的属性
        # 更新Short Option数据
        opportunity.short_option.iv = short_data["mark_iv"]
        opportunity.short_option.bid = short_data["best_bid"]
        opportunity.short_option.ask = short_data["best_ask"]
        opportunity.short_option.mid_price = short_data["mid_price"]
        opportunity.short_option.delta = short_data["greeks"]["delta"]
        opportunity.short_option.net_delta = short_data["greeks"]["net_delta"]
        opportunity.short_option.gamma = short_data["greeks"]["gamma"]
        opportunity.short_option.vega = short_data["greeks"]["vega"]
        opportunity.short_option.theta = short_data["greeks"]["theta"]
        opportunity.short_option.rho = short_data["greeks"]["rho"]
        opportunity.short_option.open_interest = short_data["open_interest"]
        
        # 更新Long Option数据
        opportunity.long_option.iv = long_data["mark_iv"]
        opportunity.long_option.bid = long_data["best_bid"]
        opportunity.long_option.ask = long_data["best_ask"]
        opportunity.long_option.mid_price = long_data["mid_price"]
        opportunity.long_option.delta = long_data["greeks"]["delta"]
        opportunity.long_option.net_delta = long_data["greeks"]["net_delta"]
        opportunity.long_option.gamma = long_data["greeks"]["gamma"]
        opportunity.long_option.vega = long_data["greeks"]["vega"]
        opportunity.long_option.theta = long_data["greeks"]["theta"]
        opportunity.long_option.rho = long_data["greeks"]["rho"]
        opportunity.long_option.open_interest = long_data["open_interest"]
        
        # 重新计算Calendar Spread衍生属性
        opportunity.iv_spread = opportunity.short_option.iv - opportunity.long_option.iv
        opportunity.iv_spread_pct = (opportunity.iv_spread / opportunity.long_option.iv) if opportunity.long_option.iv > 0 else 0
        opportunity.net_premium = opportunity.short_option.mid_price - opportunity.long_option.mid_price  # 卖出收入 - 买入成本
        opportunity.time_gap_days = opportunity.long_option.days_to_expiry - opportunity.short_option.days_to_expiry
        
        # 重新计算最大盈利潜力（简化版）
        opportunity.max_profit_potential = abs(opportunity.net_premium) * 0.5  # 简化计算
        
        # 重新评估信号强度
        opportunity.signal_strength = _evaluate_signal_strength(
            opportunity.iv_spread, opportunity.iv_spread_pct, opportunity.time_gap_days
        )
        
        print(f"✅ 完整更新Calendar Spread机会 (in-place):")
        print(f"   Combined Net Delta: {opportunity.long_option.net_delta - opportunity.short_option.net_delta:.4f}")
        print(f"   IV Spread: {opportunity.iv_spread:.4f} ({opportunity.iv_spread_pct:+.1%})")
        print(f"   Net Premium: {opportunity.net_premium:.4f}")
        print(f"   Signal Strength: {opportunity.signal_strength}")
        print(f"   对冲建议: {'做空标的' if (opportunity.long_option.net_delta - opportunity.short_option.net_delta) > 0 else '做多标的' if (opportunity.long_option.net_delta - opportunity.short_option.net_delta) < 0 else '无需对冲'}")
        
        return opportunity
        
    except Exception as e:
        print(f"❌ 更新Calendar Spread机会失败: {e}")
        if net_delta_only:
            # 返回原有的net delta
            original_net_delta = opportunity.long_option.net_delta - opportunity.short_option.net_delta
            return original_net_delta
        else:
            return opportunity 


def find_calendar_spread_options(atm_options: List[OptionData], config: Dict[str, Any]) -> List[CalendarSpreadOpportunity]:
    """
    寻找Calendar Spread期权对
    
    Args:
        atm_options: ATM期权列表（从atm_options_filter.py获得）
        config: 配置字典
        
    Returns:
        Calendar Spread机会列表
    """
    print("🔍 搜索Calendar Spread机会...")
    
    opportunities = []
    
    # 获取配置参数
    time_pairings = config["time_pairings"]["valid_combinations"]
    time_tolerance = config["time_pairings"]["time_tolerance_days"]
    min_iv_spread = config["iv_criteria"]["min_iv_spread"]
    max_results = config["search_config"]["max_results"]
    
    # 按期权类型和执行价分组
    grouped_options = _group_options_by_strike_and_type(atm_options)
    
    print(f"📊 按执行价和类型分组后有{len(grouped_options)}个组")
    
    # 对每个时间配对搜索机会
    for pairing in time_pairings:
        short_days = pairing["short_days"]
        long_days = pairing["long_days"]
        
        print(f"🔍 搜索时间配对: {short_days}天 vs {long_days}天...")
        
        # 在每个分组中寻找匹配的期权对
        for group_key, options_in_group in grouped_options.items():
            strike, option_type = group_key
            
            # 筛选短期和长期期权
            short_candidates = [
                opt for opt in options_in_group 
                if abs(opt.days_to_expiry - short_days) <= time_tolerance
            ]
            
            long_candidates = [
                opt for opt in options_in_group 
                if abs(opt.days_to_expiry - long_days) <= time_tolerance
            ]
            
            # 寻找有效的Calendar Spread配对
            for short_opt in short_candidates:
                for long_opt in long_candidates:
                    if _is_valid_calendar_pair(short_opt, long_opt, min_iv_spread):
                        opportunity = _create_calendar_opportunity(
                            short_opt, long_opt, len(opportunities) + 1
                        )
                        opportunities.append(opportunity)
    
    # 排序和限制结果
    opportunities = _sort_and_limit_opportunities(opportunities, config)
    
    print(f"✅ 找到{len(opportunities)}个Calendar Spread机会")
    
    return opportunities


def _group_options_by_strike_and_type(atm_options: List[OptionData]) -> Dict[Tuple[float, str], List[OptionData]]:
    """
    按执行价和期权类型分组
    
    Returns:
        Dict[Tuple[strike, option_type], List[OptionData]]
    """
    grouped = {}
    
    for option in atm_options:
        key = (option.strike, option.option_type)
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(option)
    
    return grouped


def _is_valid_calendar_pair(short_opt: OptionData, long_opt: OptionData, min_iv_spread: float) -> bool:
    """
    检查是否为有效的Calendar Spread配对
    
    条件：
    1. 长期期权到期时间 > 短期期权到期时间
    2. IV期限结构倒挂：short_iv > long_iv + min_iv_spread
    3. 两个期权都有有效的市场数据
    """
    
    # 1. 时间结构检查
    if long_opt.days_to_expiry <= short_opt.days_to_expiry:
        return False
    
    # 2. IV期限结构倒挂检查
    iv_spread = short_opt.iv - long_opt.iv
    if iv_spread < min_iv_spread:
        return False
    
    # 3. 市场数据有效性检查
    if (short_opt.bid <= 0 or short_opt.ask <= 0 or 
        long_opt.bid <= 0 or long_opt.ask <= 0):
        return False
    
    # 4. 价格合理性检查
    if short_opt.mid_price <= 0 or long_opt.mid_price <= 0:
        return False
    
    return True


def _create_calendar_opportunity(short_opt: OptionData, long_opt: OptionData, rank: int) -> CalendarSpreadOpportunity:
    """
    创建Calendar Spread机会对象
    """
    
    # 计算关键指标
    iv_spread = short_opt.iv - long_opt.iv
    iv_spread_pct = iv_spread / long_opt.iv if long_opt.iv > 0 else 0
    time_gap_days = long_opt.days_to_expiry - short_opt.days_to_expiry
    
    # 净保险费（买入长期 - 卖出短期）
    net_premium = long_opt.mid_price - short_opt.mid_price
    
    # 简化的最大盈利潜力估算
    # Calendar Spread的理论最大盈利 ≈ 时间价值差异
    max_profit_potential = abs(short_opt.theta - long_opt.theta) * time_gap_days / 365 * 30  # 简化估算
    
    # 信号强度评估
    signal_strength = _evaluate_signal_strength(iv_spread, iv_spread_pct, time_gap_days)
    
    return CalendarSpreadOpportunity(
        rank=rank,
        short_option=short_opt,
        long_option=long_opt,
        iv_spread=iv_spread,
        iv_spread_pct=iv_spread_pct,
        time_gap_days=time_gap_days,
        net_premium=net_premium,
        max_profit_potential=max_profit_potential,
        signal_strength=signal_strength
    )


def _evaluate_signal_strength(iv_spread: float, iv_spread_pct: float, time_gap_days: int) -> str:
    """
    评估Calendar Spread信号强度
    
    Args:
        iv_spread: IV绝对价差
        iv_spread_pct: IV相对价差
        time_gap_days: 时间间隔
        
    Returns:
        信号强度：WEAK, MODERATE, STRONG
    """
    
    # 强信号条件
    if (iv_spread >= 0.05 and iv_spread_pct >= 0.15 and time_gap_days >= 14):
        return "STRONG"
    
    # 中等信号条件
    elif (iv_spread >= 0.03 and iv_spread_pct >= 0.10 and time_gap_days >= 7):
        return "MODERATE"
    
    # 弱信号
    else:
        return "WEAK"


def _sort_and_limit_opportunities(opportunities: List[CalendarSpreadOpportunity], config: Dict[str, Any]) -> List[CalendarSpreadOpportunity]:
    """
    排序和限制机会数量
    """
    
    sort_by = config["search_config"]["sort_by"]
    sort_order = config["search_config"]["sort_order"]
    max_results = config["search_config"]["max_results"]
    
    # 排序
    if sort_by == "iv_spread":
        opportunities.sort(key=lambda x: x.iv_spread, reverse=(sort_order == "desc"))
    elif sort_by == "profit_potential":
        opportunities.sort(key=lambda x: x.max_profit_potential, reverse=(sort_order == "desc"))
    else:
        # 默认按IV价差排序
        opportunities.sort(key=lambda x: x.iv_spread, reverse=True)
    
    # 限制数量并重新排名
    limited_opportunities = opportunities[:max_results]
    for i, opp in enumerate(limited_opportunities):
        opp.rank = i + 1
    
    return limited_opportunities


def display_calendar_opportunities(opportunities: List[CalendarSpreadOpportunity]) -> None:
    """
    显示Calendar Spread机会
    """
    
    if not opportunities:
        print("❌ 未找到符合条件的Calendar Spread机会")
        return
    
    print(f"\n✅ 找到 {len(opportunities)} 个Calendar Spread机会:")
    print("=" * 100)
    
    for opp in opportunities:
        print(f"\n📊 机会 #{opp.rank} - 信号强度: {opp.signal_strength}")
        
        print(f"\n   📉 短期期权 (卖出):")
        print(f"      {opp.short_option}")
        
        print(f"\n   📈 长期期权 (买入):")
        print(f"      {opp.long_option}")
        
        print(f"\n   💰 分析:")
        print(f"      IV价差: {opp.iv_spread:+.1%} ({opp.iv_spread_pct:+.1%})")
        print(f"      时间间隔: {opp.time_gap_days}天")
        print(f"      净保险费: {opp.net_premium:+.4f} BTC {'(支出)' if opp.net_premium < 0 else '(收入)'}")
        print(f"      预期盈利潜力: {opp.max_profit_potential:.4f} BTC")
        
        print("-" * 100)

if __name__ == "__main__":

        # 加载配置
    with open("calendar_spread.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # 1. 获取ATM期权（来自atm_options_filter.py）
    atm_options = get_atm_options(config, "BTC", "testnet")

    # 2. 搜索Calendar Spread机会
    opportunities = find_calendar_spread_options(atm_options, config)

    # 3. 显示结果
    display_calendar_opportunities(opportunities)