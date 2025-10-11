#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试精确P&L集成功能
验证RiskManager使用新的精确P&L API
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from qtrade.cryptotrader.trading_engine.risk_manager import RiskManager
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.atm_options_filter import OptionData


def create_mock_straddle_opportunity():
    """创建模拟的Straddle机会，使用真实存在的合约"""
    
    # 使用真实存在的合约
    call_option = OptionData(
        symbol="BTC-28NOV25-114000-C",
        strike=114000,
        expiry="28NOV25",
        days_to_expiry=18,
        option_type="C",
        iv=0.66,
        bid=0.0570,
        ask=0.0590,
        mid_price=0.0580,
        delta=0.15,
        net_delta=0.09,  # delta - mid_price approximation
        gamma=0.00001,
        theta=-0.0005,
        vega=0.02,
        rho=0.001
    )
    
    # 创建一个虚拟的Put期权（用于测试，实际中可能不存在）
    put_option = OptionData(
        symbol="BTC-28NOV25-114000-P",
        strike=114000,
        expiry="28NOV25",
        days_to_expiry=18,
        option_type="P",
        iv=0.66,
        bid=0.0570,
        ask=0.0590,
        mid_price=0.0580,
        delta=-0.85,
        net_delta=-0.91,  # delta - mid_price approximation
        gamma=0.00001,
        theta=-0.0005,
        vega=0.02,
        rho=-0.001
    )
    
    opportunity = StraddleOpportunity(
        call_option=call_option,
        put_option=put_option,
        spot_price=63000,
        realized_vol=0.60
    )
    
    # 模拟已开仓状态
    opportunity.open_status = True
    opportunity.contracts = 1.0
    
    return opportunity


def test_precise_pnl_integration():
    """测试精确P&L集成功能"""
    
    print("🚀 精确P&L集成测试")
    print("=" * 60)
    
    try:
        # 创建RiskManager实例
        risk_manager = RiskManager(
            max_positions=6,  # 总共最多6个持仓
            enable_delta_hedge=True,
            delta_risk_threshold=0.5
        )
        
        print("✅ RiskManager创建成功")
        
        # 创建模拟的Straddle机会
        mock_opportunity = create_mock_straddle_opportunity()
        print(f"✅ 模拟Straddle机会创建: {mock_opportunity.call_option.symbol}")
        
        print("\n📊 测试精确P&L获取:")
        print("-" * 40)
        
        # 测试精确P&L获取
        precise_pnl = risk_manager.get_opened_opportunities_pnl(mock_opportunity, "testnet")
        
        print(f"📈 精确P&L结果: {precise_pnl:.8f} BTC")
        
        if abs(precise_pnl) > 1e-8:
            print("✅ 成功获取到非零P&L，精确P&L功能正常工作")
            
            # 测试平仓条件检查
            print(f"\n🔍 测试平仓条件检查:")
            print("-" * 40)
            
            should_close, reason = risk_manager.check_close_condition(mock_opportunity, "testnet")
            print(f"平仓建议: {'是' if should_close else '否'}")
            print(f"原因: {reason}")
            
        else:
            print("⚠️ 获取到零P&L，可能是因为:")
            print("   1. 持仓不存在")
            print("   2. P&L确实为0")
            print("   3. API调用失败")
        
        print("\n🔧 对比分析:")
        print("-" * 40)
        
        # 直接调用新的精确P&L API进行对比
        from qtrade.order_api.deribit_order_placer.positions_info import get_precise_total_pnl_for_instruments
        
        instruments = [mock_opportunity.call_option.symbol]  # 只测试真实存在的合约
        direct_result = get_precise_total_pnl_for_instruments(instruments, "testnet")
        
        print(f"直接API调用结果:")
        print(f"   精确P&L: {direct_result['total_precise_pnl']:.8f} BTC")
        print(f"   数据来源: {direct_result['data_source']}")
        print(f"   精度级别: {direct_result['precision_level']}")
        print(f"   找到持仓: {direct_result['found_count']}/{direct_result['total_instruments']}")
        
        print("\n✅ 精确P&L集成测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_precise_pnl_integration()
