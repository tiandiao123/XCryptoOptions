#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar Spread交易执行测试
演示协同下单策略 + RiskManager集成
"""

import yaml
import threading
from typing import Optional

from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import get_okx_atm_options
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import (
    display_calendar_opportunities, 
    find_calendar_spread_options
)
from qtrade.optionstrader.arbitrage_searcher.option_data import CalendarSpreadOpportunity
from qtrade.optionstrader.order_exp.async_coordinated_order_placer import place_calendar_spread_async
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager


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
    risk_manager: Optional[OKXRiskManager] = None,
    simulated: bool = True,
    price_offset_ticks: int = 1,
    poll_interval: float = 0.3
):
    """
    执行Calendar Spread异步协同下单 + RiskManager集成
    
    Args:
        opportunity: Calendar Spread机会
        crypto_notional: 交易数量（币本位）
        risk_manager: 风险管理器实例（如果提供，成交后自动加入监控）
        simulated: 是否模拟盘
        price_offset_ticks: 价格偏移（tick数量）
        poll_interval: 轮询间隔
    
    Returns:
        执行结果
    """
    print(f"\n{'='*70}")
    print(f"🚀 执行Calendar Spread异步协同下单")
    print(f"{'='*70}")
    
    # 执行协同下单
    result = place_calendar_spread_async(
        opportunity=opportunity,
        crypto_notional=crypto_notional,
        simulated=simulated,
        price_offset_ticks=price_offset_ticks,
        poll_interval=poll_interval,
        trigger_fill_ratio=1.0  # 完全成交才触发
    )
    
    # 如果成交成功且提供了RiskManager，加入监控
    if result.get("success") and risk_manager:
        print(f"\n{'='*70}")
        print(f"🛡️  将持仓加入RiskManager监控")
        print(f"{'='*70}")
        
        # 设置持仓信息
        opportunity.open_status = True
        opportunity.contracts = crypto_notional
        
        # 记录开仓IV
        opportunity.short_option_entry_iv = opportunity.short_option.iv
        opportunity.long_option_entry_iv = opportunity.long_option.iv
        
        # 加入RiskManager
        add_result = risk_manager.add_position(opportunity)
        
        if add_result.get("success"):
            print(f"✅ 持仓已加入RiskManager")
            print(f"   Position Key: {add_result['position_key']}")
            print(f"   当前持仓数: {risk_manager.get_position_count()['calendar_spread']}")
            print(f"\n📊 风控参数:")
            print(f"   止损比率: {risk_manager.stop_loss_ratio:.1%}")
            print(f"   止盈比率: {risk_manager.profit_target_ratio:.1%}")
            print(f"   Delta对冲: {'启用' if risk_manager.enable_delta_hedge else '禁用'}")
            
            # 将result扩展
            result["risk_manager_added"] = True
            result["position_key"] = add_result["position_key"]
        else:
            print(f"⚠️  加入RiskManager失败: {add_result.get('error')}")
            result["risk_manager_added"] = False
    
    return result


if __name__ == "__main__":
    # 配置
    calendar_config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    
    # Step 1: 获取交易机会
    print("\n" + "="*70)
    print("📊 Calendar Spread 协同下单 + 风控监控测试")
    print("="*70)
    
    opportunity = get_calendar_spread_opportunity(
        config_path=calendar_config_path, 
        currency="ETH",
        show_details=False  # 简化输出
    )
    
    if not opportunity:
        print("\n❌ 未找到交易机会，退出")
        exit(1)
    
    # Step 2: 初始化RiskManager
    print(f"\n{'='*70}")
    print(f"🛡️  初始化RiskManager")
    print(f"{'='*70}")
    
    env = "mainnet"  # testnet 或 mainnet
    
    risk_manager = OKXRiskManager(
        symbol="ETHUSD",  # ETH期权
        max_positions=5,
        enable_delta_hedge=True,
        delta_hedge_threshold=0.05,
        stop_loss_ratio=-0.3,      # -30% 止损
        profit_target_ratio=0.5,   # +50% 止盈
        price_change_risk_ratio=0.15,
        env=env
    )
    
    print(f"✅ RiskManager初始化完成")
    print(f"   Max Positions: {risk_manager.max_positions}")
    print(f"   Delta Hedge: {risk_manager.enable_delta_hedge}")
    print(f"   Stop Loss: {risk_manager.stop_loss_ratio:.1%}")
    print(f"   Profit Target: {risk_manager.profit_target_ratio:.1%}")
    
    # Step 3: 启动RiskManager监控线程
    print(f"\n🔍 启动RiskManager后台监控线程...")
    
    def start_risk_monitoring():
        """后台监控线程"""
        try:
            risk_manager.monitor_positions(check_duration="5min")
        except KeyboardInterrupt:
            print(f"\n🛑 监控线程收到中断信号")
        except Exception as e:
            print(f"\n❌ 监控线程异常: {e}")
    
    monitoring_thread = threading.Thread(
        target=start_risk_monitoring,
        daemon=True,
        name="RiskMonitor"
    )
    monitoring_thread.start()
    print(f"✅ 监控线程已启动 (线程ID: {monitoring_thread.ident})")
    
    # Step 4: 确认交易参数
    crypto_notional = 0.1  # 0.1 ETH
    simulated = (env == "testnet")
    
    print(f"\n📋 交易参数:")
    print(f"   币种: ETH")
    print(f"   数量: {crypto_notional} ETH")
    print(f"   环境: {'🧪 DEMO' if simulated else '🔴 LIVE'}")
    print(f"   策略: 异步协同下单 + 自动风控")
    print(f"   Price Offset: 1 tick")
    
    # Step 5: 执行交易
    user_confirm = input(f"\n⚠️  是否继续执行交易? (yes/no): ")
    
    if user_confirm.lower() in ('yes', 'y'):
        try:
            result = execute_calendar_spread_trade(
                opportunity=opportunity,
                crypto_notional=crypto_notional,
                risk_manager=risk_manager,  # 🆕 传入RiskManager
                simulated=simulated,
                price_offset_ticks=1,
                poll_interval=0.3
            )
            
            if result.get("success"):
                print(f"\n{'='*70}")
                print(f"🎉 交易执行成功！")
                print(f"{'='*70}")
                print(f"   总耗时: {result['total_time']:.2f}秒")
                print(f"   触发腿: {result['winner'].upper()}")
                
                if result.get("risk_manager_added"):
                    print(f"\n🛡️  持仓已纳入风控监控")
                    print(f"   Position Key: {result.get('position_key')}")
                    print(f"\n📊 RiskManager将自动执行:")
                    print(f"   ✅ 实时P&L监控")
                    print(f"   ✅ 止损/止盈检查")
                    print(f"   ✅ IV反转监控")
                    print(f"   ✅ Delta对冲（如触发）")
                    print(f"\n💡 监控线程将持续运行...")
                    print(f"   按Ctrl+C退出")
                    
                    # 保持主线程运行，让监控线程继续工作
                    try:
                        import time
                        while True:
                            time.sleep(10)
                            # 定期显示持仓状态
                            positions = risk_manager.get_position_count()
                            print(f"\n📊 [{threading.current_thread().name}] 持仓状态: Calendar={positions['calendar_spread']}, Straddle={positions['straddle']}")
                    except KeyboardInterrupt:
                        print(f"\n\n🛑 用户中断，退出监控")
                
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

