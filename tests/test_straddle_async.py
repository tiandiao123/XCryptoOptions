#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Straddle 异步协同下单功能
"""

from qtrade.optionstrader.arbitrage_searcher.option_data import StraddleOpportunityOKX, OptionData
from qtrade.optionstrader.master_trader.async_coordinated_order_placer import (
    place_straddle_async,
    close_straddle_async
)


def create_test_straddle() -> StraddleOpportunityOKX:
    """创建一个测试用的 Straddle 对象"""
    
    # Call 期权
    call_option = OptionData(
        symbol="ETH-USD-251226-3200-C",
        strike=3200.0,
        expiry="251226",
        days_to_expiry=37,
        option_type="C",
        iv=0.75,
        bid=0.095,
        ask=0.097,
        mid_price=0.096,
        delta=0.48,
        net_delta=0.48,
        gamma=0.001,
        vega=2.5,
        theta=-0.1,
        rho=0.5,
        open_interest=100
    )
    
    # Put 期权
    put_option = OptionData(
        symbol="ETH-USD-251226-3200-P",
        strike=3200.0,
        expiry="251226",
        days_to_expiry=37,
        option_type="P",
        iv=0.74,
        bid=0.088,
        ask=0.090,
        mid_price=0.089,
        delta=-0.52,
        net_delta=-0.52,
        gamma=0.001,
        vega=2.5,
        theta=-0.1,
        rho=-0.5,
        open_interest=100
    )
    
    # 创建 Straddle 对象
    straddle = StraddleOpportunityOKX(
        call_option=call_option,
        put_option=put_option,
        strategy_type="short_straddle",
        avg_iv=0.745,
        realized_vol=0.60,
        iv_premium=0.145,
        iv_premium_pct=24.17,
        call_option_entry_iv=0.75,
        put_option_entry_iv=0.74,
        entry_spot_price=3200.0,
        total_premium=0.185  # call_mid + put_mid
    )
    
    return straddle


def test_straddle_open():
    """测试 Straddle 开仓"""
    print("=" * 70)
    print("🧪 测试 Straddle 异步开仓")
    print("=" * 70)
    
    straddle = create_test_straddle()
    
    print(f"\n📊 Straddle 详情:")
    print(f"   Call: {straddle.call_option.symbol} @ {straddle.call_option.mid_price:.4f}")
    print(f"   Put:  {straddle.put_option.symbol} @ {straddle.put_option.mid_price:.4f}")
    print(f"   总权利金: {straddle.total_premium:.4f} ETH")
    print(f"   IV溢价: {straddle.iv_premium_pct:.1f}%")
    
    # 执行开仓（模拟盘）
    result = place_straddle_async(
        opportunity=straddle,
        crypto_notional=1.0,  # 1 ETH
        simulated=True,       # 模拟盘
        price_offset_ticks=1,
        poll_interval=0.3
    )
    
    print(f"\n✅ 开仓结果:")
    print(f"   成功: {result.get('success')}")
    print(f"   总耗时: {result.get('total_time', 0):.2f}秒")
    if result.get('winner'):
        print(f"   先成交: {result.get('winner').upper()}")
    
    return result


def test_straddle_close():
    """测试 Straddle 平仓"""
    print("\n" + "=" * 70)
    print("🧪 测试 Straddle 异步平仓")
    print("=" * 70)
    
    straddle = create_test_straddle()
    
    # 执行平仓（保守模式）
    result = close_straddle_async(
        opportunity=straddle,
        crypto_notional=1.0,
        simulated=True,
        aggressive=False  # 保守模式
    )
    
    print(f"\n✅ 平仓结果:")
    print(f"   成功: {result.get('success')}")
    print(f"   总耗时: {result.get('total_time', 0):.2f}秒")
    
    return result


if __name__ == "__main__":
    print("\n" + "🚀" * 35)
    print("Straddle 异步协同下单测试")
    print("🚀" * 35 + "\n")
    
    # 测试开仓
    # open_result = test_straddle_open()
    
    # 测试平仓
    # close_result = test_straddle_close()
    
    print("\n" + "=" * 70)
    print("💡 提示:")
    print("=" * 70)
    print("1. 开仓：Call卖 + Put卖（双卖）")
    print("2. 平仓：Call买 + Put买（双买）")
    print("3. 监控：任一腿成交立即响应（0.3秒轮询）")
    print("4. 收尾：撤单 + Aggressive成交另一腿")
    print("\n📝 使用方法:")
    print("   from qtrade.optionstrader.master_trader.async_coordinated_order_placer import (")
    print("       place_straddle_async,")
    print("       close_straddle_async")
    print("   )")
    print("\n   # 开仓")
    print("   result = place_straddle_async(straddle, crypto_notional=1.0)")
    print("\n   # 平仓（保守模式）")
    print("   result = close_straddle_async(straddle, crypto_notional=1.0, aggressive=False)")
    print("\n   # 平仓（激进模式）")
    print("   result = close_straddle_async(straddle, crypto_notional=1.0, aggressive=True)")
    print("=" * 70)



