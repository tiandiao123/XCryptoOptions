# -*- coding: utf-8 -*-
"""
Gamma Scalping - OKX ATM期权筛选器
专门为Selling Straddle策略筛选合适的OKX ATM期权
"""

import yaml
import numpy as np
from typing import List, Dict, Any, Tuple
from datetime import datetime

# 复用OKX ATM获取器和基础数据结构
from qtrade.optionstrader.arbitrage_searcher.option_data import OptionData
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import (
    get_okx_atm_options
)


def get_straddle_atm_options_okx(config: Dict[str, Any], currency: str = "BTC") -> List[OptionData]:
    """
    获取适合Selling Straddle的OKX ATM期权
    
    Args:
        config: Selling Straddle配置字典
        currency: 币种 (BTC/ETH)
        
    Returns:
        筛选后的ATM期权列表
    """
    print(f"🔍 [OKX] 获取{currency} Selling Straddle ATM期权...")
    
    try:
        # 1. 获取OKX ATM期权（已包含IV/Greeks/价格/OI）
        atm_options = get_okx_atm_options(config, currency=currency)
        
        if not atm_options:
            print("❌ 未找到ATM期权")
            return []
        
        # 2. 应用Selling Straddle特定的筛选条件
        straddle_options = _filter_straddle_options_okx(atm_options, config)
        
        print(f"✅ [OKX] Selling Straddle筛选后剩余 {len(straddle_options)} 个期权")
        
        return straddle_options
        
    except Exception as e:
        print(f"❌ 获取OKX Selling Straddle ATM期权失败: {e}")
        import traceback
        traceback.print_exc()
        return []


def _filter_straddle_options_okx(options: List[OptionData], config: Dict[str, Any]) -> List[OptionData]:
    """
    应用Selling Straddle特定的筛选条件 - OKX版本
    
    Args:
        options: OKX ATM期权列表
        config: Selling Straddle配置字典
        
    Returns:
        筛选后的期权列表
    """
    
    # 获取配置参数
    time_criteria = config.get("time_criteria", {})
    min_days = time_criteria.get("min_days_to_expiry", 7)
    max_days = time_criteria.get("max_days_to_expiry", 25)
    
    pairing_criteria = config.get("pairing_criteria", {})
    min_iv = pairing_criteria.get("min_iv", 0.01)
    max_iv = pairing_criteria.get("max_iv", 3.0)
    min_option_price = pairing_criteria.get("min_option_price", 0.0001)
    
    market_filters = config.get("market_filters", {})
    liquidity = market_filters.get("liquidity", {})
    
    filtered_options = []
    
    print(f"📋 应用Straddle筛选条件: DTE={min_days}-{max_days}天, IV={min_iv:.1%}-{max_iv:.1%}")
    
    for option in options:
        try:
            # 1. 时间筛选
            if not (min_days <= option.days_to_expiry <= max_days):
                continue
            
            # 2. IV合理性检查
            if not (min_iv <= option.iv <= max_iv):
                continue
            
            # 3. 价格有效性检查
            if option.mid_price < min_option_price:
                continue
            
            # 4. 流动性检查（OKX可能bid/ask为0，用mid兜底）
            if liquidity:
                min_bid = liquidity.get("min_bid_price", 0)
                max_spread_pct = liquidity.get("max_bid_ask_spread_pct", 1.0)
                
                # 如果有bid/ask，检查价差
                if option.bid > 0 and option.ask > 0:
                    if option.bid < min_bid:
                        continue
                    if option.mid_price > 0:
                        spread_pct = (option.ask - option.bid) / option.mid_price
                        if spread_pct > max_spread_pct:
                            continue
            
            filtered_options.append(option)
            
        except Exception as e:
            print(f"⚠️ 筛选期权{option.symbol}时出错: {e}")
            continue
    
    return filtered_options


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


def load_straddle_config_okx(config_path: str = None) -> Dict[str, Any]:
    """
    加载OKX Selling Straddle配置文件
    
    Args:
        config_path: 配置文件路径
        
    Returns:
        配置字典
    """
    if config_path is None:
        # 尝试多个可能的路径
        possible_paths = [
            "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/gamma_scalping/selling_straddle_okx.yaml",
            "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
        ]
        
        for path in possible_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                print(f"✅ 加载配置: {path}")
                return config
            except FileNotFoundError:
                continue
        
        print("⚠️ 未找到配置文件，使用默认配置")
        return get_default_straddle_config_okx()
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}，使用默认配置")
        return get_default_straddle_config_okx()


def get_default_straddle_config_okx() -> Dict[str, Any]:
    """默认OKX Selling Straddle配置"""
    return {
        "time_criteria": {
            "min_days_to_expiry": 7,
            "max_days_to_expiry": 25
        },
        "strike_criteria": {
            "atm_tolerance_pct": 0.03  # OKX用3%
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
                "min_open_interest": 0  # OKX OI可能为0
            }
        }
    }


if __name__ == "__main__":
    # 测试OKX Selling Straddle ATM期权筛选
    print("🚀 测试OKX Selling Straddle ATM期权筛选...")
    
    # 加载配置
    config = load_straddle_config_okx()
    
    # 获取ATM期权
    straddle_options = get_straddle_atm_options_okx(config, "BTC")
    
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
        
        # 显示前几个配对
        for i, (call, put) in enumerate(pairs[:5], 1):  # 只显示前5个
            total_premium = call.mid_price + put.mid_price
            avg_iv = (call.iv + put.iv) / 2
            
            print(f"\n   📊 Straddle配对 #{i}:")
            print(f"      🔵 Call: {call.symbol}")
            print(f"         执行价: ${call.strike:,.0f} | 到期: {call.days_to_expiry}天 | IV: {call.iv:.1%}")
            print(f"         价格: Bid={call.bid:.4f}, Ask={call.ask:.4f}, Mid={call.mid_price:.4f}")
            print(f"         希腊字母: Δ={call.delta:+.4f}, Γ={call.gamma:+.4f}, Θ={call.theta:+.4f}")
            
            print(f"      🔴 Put:  {put.symbol}")
            print(f"         执行价: ${put.strike:,.0f} | 到期: {put.days_to_expiry}天 | IV: {put.iv:.1%}")
            print(f"         价格: Bid={put.bid:.4f}, Ask={put.ask:.4f}, Mid={put.mid_price:.4f}")
            print(f"         希腊字母: Δ={put.delta:+.4f}, Γ={put.gamma:+.4f}, Θ={put.theta:+.4f}")
            
            # 从symbol提取币种
            currency = call.symbol.split("-")[0] if "-" in call.symbol else "UNKNOWN"
            
            print(f"      💰 Straddle总览:")
            print(f"         总权利金: {total_premium:.4f} {currency}")
            print(f"         平均IV: {avg_iv:.1%}")
            print(f"         净Delta: {call.delta + put.delta:+.4f}")
            print(f"         总Gamma: {call.gamma + put.gamma:+.4f}")
            print(f"         总Theta: {call.theta + put.theta:+.4f}")
    else:
        print("❌ 未找到适合的期权")

