#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar Spread交易执行测试
演示协同下单策略
"""

import yaml
from typing import Optional

from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import get_okx_atm_options
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import (
    display_calendar_opportunities, 
    find_calendar_spread_options
)
from qtrade.optionstrader.arbitrage_searcher.option_data import CalendarSpreadOpportunity
from qtrade.optionstrader.order_exp.coordinated_order_placer import place_calendar_spread_coordinated


def get_calendar_spread_opportunity(
    config_path: str, 
    currency: str = "ETH",
    show_details: bool = True
) -> Optional[CalendarSpreadOpportunity]:
    """
    获取Calendar Spread交易机会
    
    Args:
        config_path: 配置文件路径
        currency: 币种 (BTC/ETH)
        show_details: 是否显示详细信息
    
    Returns:
        最佳Calendar Spread机会（如果有）
    """
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 1. 获取ATM期权
    print(f"\n🔍 [Step 1] 获取{currency} ATM期权...")
    atm_options = get_okx_atm_options(config, currency)
    
    if not atm_options:
        print("❌ 未找到ATM期权")
        return None
    
    print(f"✅ 找到 {len(atm_options)} 个ATM期权")

    if show_details:
        for opt in atm_options:
            print("=" * 60)
            print(f"📌 {opt.symbol}")
            print(f"   执行价: ${opt.strike:,.2f}")
            print(f"   报价: Bid {opt.bid:.4f} / Ask {opt.ask:.4f} / Mid {opt.mid_price:.4f}")
            print(f"   波动率(IV): {opt.iv:.2%}")
            print(f"   持仓量(OI): {opt.open_interest}")
            print(f"   希腊字母: Δ {opt.delta:+.4f} | Γ {opt.gamma:+.4f} | ν {opt.vega:+.4f} | Θ {opt.theta:+.4f}")
            print(f"   到期: {opt.expiry} | 剩余: {opt.days_to_expiry} 天 | 类型: {opt.option_type}")

    # 2. 搜索Calendar Spread机会
    print(f"\n🔍 [Step 2] 搜索Calendar Spread机会...")
    opportunities = find_calendar_spread_options(atm_options, config)

    if not opportunities:
        print("❌ 未找到Calendar Spread机会")
        return None

    # 3. 显示结果
    display_calendar_opportunities(opportunities)

    # 返回最佳机会
    best_opportunity = opportunities[0]
    print(f"\n✅ 最佳机会: Rank #{best_opportunity.rank}")
    print(f"   Short: {best_opportunity.short_option.symbol}")
    print(f"   Long:  {best_opportunity.long_option.symbol}")
    print(f"   IV价差: {best_opportunity.iv_spread:+.1%}")
    
    return best_opportunity


def execute_calendar_spread_trade(
    opportunity: CalendarSpreadOpportunity,
    crypto_notional: float,
    simulated: bool = True,
    price_offset: float = 0.0001,
    poll_interval: float = 0.5
):
    """
    执行Calendar Spread协同下单
    
    Args:
        opportunity: Calendar Spread机会
        crypto_notional: 交易数量（币本位）
        simulated: 是否模拟盘
        price_offset: 价格偏移
        poll_interval: 轮询间隔
    
    Returns:
        执行结果
    """
    print(f"\n{'='*70}")
    print(f"🚀 执行Calendar Spread协同下单")
    print(f"{'='*70}")
    
    result = place_calendar_spread_coordinated(
        opportunity=opportunity,
        crypto_notional=crypto_notional,
        simulated=simulated,
        price_offset=price_offset,
        poll_interval=poll_interval,
        trigger_ratio=1.0  # 完全成交才触发
    )
    
    return result


if __name__ == "__main__":
    # 配置
    calendar_config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    
    # Step 1: 获取交易机会
    print("\n" + "="*70)
    print("📊 Calendar Spread 协同下单测试")
    print("="*70)
    
    opportunity = get_calendar_spread_opportunity(
        config_path=calendar_config_path, 
        currency="ETH",
        show_details=False  # 简化输出
    )
    
    if not opportunity:
        print("\n❌ 未找到交易机会，退出")
        exit(1)
    
    # Step 2: 确认交易参数
    crypto_notional = 0.1  # 0.1 ETH
    simulated = True       # 模拟盘
    
    print(f"\n📋 交易参数:")
    print(f"   币种: ETH")
    print(f"   数量: {crypto_notional} ETH")
    print(f"   环境: {'🧪 DEMO' if simulated else '🔴 LIVE'}")
    print(f"   策略: 协同下单（被动挂单+触发跟随）")
    
    # Step 3: 执行交易
    user_confirm = input(f"\n⚠️  是否继续执行交易? (yes/no): ")
    
    if user_confirm.lower() in ('yes', 'y'):
        try:
            result = execute_calendar_spread_trade(
                opportunity=opportunity,
                crypto_notional=crypto_notional,
                simulated=simulated,
                price_offset=0.0001,
                poll_interval=0.5
            )
            
            if result.get("success"):
                print(f"\n🎉 交易执行成功！")
                print(f"   总耗时: {result['total_time']:.2f}秒")
                print(f"   触发腿: {result['winner'].upper()}")
            else:
                print(f"\n❌ 交易执行失败: {result.get('error')}")
                
        except KeyboardInterrupt:
            print(f"\n\n⚠️  用户中断")
        except Exception as e:
            print(f"\n❌ 交易异常: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("\n❌ 用户取消交易")

