#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamma Scalping - Selling Straddle 一次性交易测试
演示完整流程：寻找机会 → 开仓 → Delta对冲监控 → 平仓 → 结束

策略逻辑：
1. 卖出 ATM Straddle（Call + Put）收取权利金
2. 启用 Delta 对冲（Gamma Scalping）
3. RiskManager 监控持仓：
   - 实时 P&L 监控
   - Delta 对冲（标的价格波动时自动对冲）
   - 止损/止盈检查
   - IV 反转监控
4. 到期或触发条件后平仓
"""

import time
from datetime import datetime
from typing import Optional

from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder_okx import (
    SellingStraddleFinderOKX
)
from qtrade.optionstrader.arbitrage_searcher.option_data import StraddleOpportunityOKX
from qtrade.optionstrader.master_trader.async_order.async_straddle_order_placer import place_straddle_async
from qtrade.optionstrader.risk_manager.okx_risk_manager import OKXRiskManager


def get_selling_straddle_opportunity(
    config_path: str,
    currency: str = "ETH",
    show_details: bool = True
) -> Optional[StraddleOpportunityOKX]:
    """
    获取 Selling Straddle 交易机会
    
    Args:
        config_path: 配置文件路径
        currency: 币种 (BTC/ETH)
        show_details: 是否显示详细信息
    
    Returns:
        最佳 Selling Straddle 机会（如果有）
    """
    print(f"\n🔍 [Step 1] 寻找 {currency} Selling Straddle 机会...")
    
    # 初始化寻找器
    finder = SellingStraddleFinderOKX(config_path, currency)
    
    # 搜索机会
    opportunities = finder.find_selling_straddle_opportunities()
    
    if not opportunities:
        print("❌ 未找到 Selling Straddle 机会")
        return None
    
    # 显示结果
    if show_details:
        finder.display_opportunities(opportunities, detailed=True)
    
    # 返回最佳机会（已按评分排序）
    best_opportunity = opportunities[0]
    print(f"\n✅ 最佳机会:")
    print(f"   Call: {best_opportunity.call_option.symbol}")
    print(f"   Put:  {best_opportunity.put_option.symbol}")
    print(f"   执行价: ${best_opportunity.strike_price:,.0f}")
    print(f"   到期天数: {best_opportunity.days_to_expiry} 天")
    print(f"   IV Premium: {best_opportunity.iv_premium_pct:+.1f}%")
    print(f"   总权利金: {best_opportunity.total_premium:.4f} {currency}")
    print(f"   评分: {best_opportunity.score:.2f}")
    
    return best_opportunity


def execute_selling_straddle_trade(
    opportunity: StraddleOpportunityOKX,
    crypto_notional: float,
    risk_manager: Optional[OKXRiskManager] = None,
    simulated: bool = True,
    price_offset_ticks: int = 1,
    poll_interval: float = 0.3
):
    """
    执行 Selling Straddle 异步协同下单 + RiskManager 集成
    
    Args:
        opportunity: Selling Straddle 机会
        crypto_notional: 交易数量（币本位）
        risk_manager: 风险管理器实例（如果提供，成交后自动加入监控）
        simulated: 是否模拟盘
        price_offset_ticks: 价格偏移（tick数量）
        poll_interval: 轮询间隔
    
    Returns:
        执行结果
    """
    print(f"\n{'='*70}")
    print(f"🚀 执行 Selling Straddle 异步协同下单")
    print(f"{'='*70}")
    
    # 执行协同下单（卖出 Call + Put）
    result = place_straddle_async(
        opportunity=opportunity,
        crypto_notional=crypto_notional,
        simulated=simulated,
        price_offset_ticks=price_offset_ticks,
        poll_interval=poll_interval,
        trigger_fill_ratio=1.0  # 完全成交才触发
    )
    
    # 如果成交成功且提供了 RiskManager，加入监控
    if result.get("success") and risk_manager:
        print(f"\n{'='*70}")
        print(f"🛡️  将持仓加入 RiskManager 监控（启用 Gamma Scalping）")
        print(f"{'='*70}")
        
        # 设置持仓信息
        opportunity.open_status = True
        opportunity.contracts = crypto_notional
        
        # 记录开仓 IV
        opportunity.call_option_entry_iv = opportunity.call_option.iv
        opportunity.put_option_entry_iv = opportunity.put_option.iv
        
        # 🆕 记录开仓价格（从 result 中获取实际成交价）
        call_sell = result.get("call_open")
        put_sell = result.get("put_open")
        if call_sell and hasattr(call_sell, 'avg_px'):
            opportunity.call_option.entry_price = float(call_sell.avg_px)
        if put_sell and hasattr(put_sell, 'avg_px'):
            opportunity.put_option.entry_price = float(put_sell.avg_px)
        
        # 加入 RiskManager
        add_success = risk_manager.add_position(opportunity)
        
        if add_success:
            # 构造 position_key 用于显示
            position_key = f"straddle_{opportunity.call_option.symbol}_{opportunity.put_option.symbol}"
            
            print(f"✅ 持仓已加入 RiskManager")
            print(f"   Position Key: {position_key}")
            print(f"   当前持仓数: {risk_manager.get_position_count()['straddle']}")
            print(f"\n📊 风控参数:")
            print(f"   止损比率: {risk_manager.stop_loss_ratio:.1%}")
            print(f"   止盈比率: {risk_manager.profit_target_ratio:.1%}")
            print(f"   Delta对冲: {'✅ 启用 (Gamma Scalping)' if risk_manager.enable_delta_hedge else '❌ 禁用'}")
            if risk_manager.enable_delta_hedge:
                print(f"   Delta阈值: {risk_manager.delta_hedge_threshold}")
                print(f"   对冲频率: 每 {risk_manager.hedge_freq} 个监控周期")
            
            # 将 result 扩展
            result["risk_manager_added"] = True
            result["position_key"] = position_key
        else:
            print(f"⚠️  加入 RiskManager 失败（持仓已满或已存在）")
            result["risk_manager_added"] = False
    
    return result


if __name__ == "__main__":
    # ==================== 配置 ====================
    straddle_config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
    env = "testnet"  # testnet 或 mainnet
    crypto_notional = 0.1  # 交易数量（ETH）
    
    print("\n" + "="*70)
    print("📊 Gamma Scalping - Selling Straddle 单次交易测试")
    print("="*70)
    print(f"   环境: {'🧪 DEMO' if env == 'testnet' else '🔴 LIVE'}")
    print(f"   数量: {crypto_notional} ETH")
    print(f"   策略: 卖出 Straddle → Delta对冲 → 监控 → 平仓")
    print("="*70)
    
    # ==================== Step 1: 寻找交易机会 ====================
    print(f"\n{'='*70}")
    print(f"🔍 寻找 Selling Straddle 机会...")
    print(f"{'='*70}")
    
    opportunity = None
    search_attempts = 0
    
    while opportunity is None:
        search_attempts += 1
        print(f"   尝试 #{search_attempts}...")
        
        opportunity = get_selling_straddle_opportunity(
            config_path=straddle_config_path,
            currency="ETH",
            show_details=False
        )
        
        if opportunity:
            print(f"\n✅ 找到交易机会！")
            print(f"   Call: {opportunity.call_option.symbol}")
            print(f"   Put:  {opportunity.put_option.symbol}")
            print(f"   IV Premium: {opportunity.iv_premium_pct:+.1f}%")
            print(f"   总权利金: {opportunity.total_premium:.4f} ETH")
            break
        else:
            print(f"   未找到机会，等待30秒后重试...")
            time.sleep(30)
    
    # ==================== Step 2: 初始化 RiskManager ====================
    print(f"\n{'='*70}")
    print(f"🛡️  初始化 RiskManager（启用 Gamma Scalping）")
    print(f"{'='*70}")
    
    risk_manager = OKXRiskManager(
        symbol="ETHUSD",  # ETH期权
        max_positions=5,
        enable_delta_hedge=True,       # 🔥 启用 Delta 对冲（Gamma Scalping）
        delta_hedge_threshold=0.05,    # Delta 阈值：±0.05
        stop_loss_ratio=-0.50,         # -50% 止损（Selling Straddle 风险较大）
        profit_target_ratio=0.30,      # +30% 止盈（收敛策略）
        price_change_risk_ratio=0.1,
        hedge_freq=30,  # 每10个监控周期执行一次对冲检查（约15分钟）
        env=env
    )
    
    print(f"✅ RiskManager 初始化完成")
    print(f"   Max Positions: {risk_manager.max_positions}")
    print(f"   Delta Hedge: ✅ 启用（Gamma Scalping 模式）")
    print(f"   Delta Threshold: {risk_manager.delta_hedge_threshold}")
    print(f"   Hedge Frequency: 每 {risk_manager.hedge_freq} 个监控周期")
    print(f"   Stop Loss: {risk_manager.stop_loss_ratio:.1%}")
    print(f"   Profit Target: {risk_manager.profit_target_ratio:.1%}")
    
    # ==================== Step 3: 执行交易 ====================
    simulated = (env == "testnet")
    start_time = datetime.now()
    
    print(f"\n📋 执行交易参数:")
    print(f"   币种: ETH")
    print(f"   数量: {crypto_notional} ETH")
    print(f"   环境: {'🧪 DEMO' if simulated else '🔴 LIVE'}")
    print(f"   Price Offset: 1 tick")
    
    result = execute_selling_straddle_trade(
        opportunity=opportunity,
        crypto_notional=crypto_notional,
        risk_manager=risk_manager,
        simulated=simulated,
        price_offset_ticks=1,
        poll_interval=0.3
    )
    
    if result.get("success"):
        print(f"\n{'='*70}")
        print(f"✅ 交易执行成功！")
        print(f"{'='*70}")
        print(f"   总耗时: {result['total_time']:.2f}秒")
        print(f"   触发腿: {result['winner'].upper()}")
        print(f"   Position Key: {result.get('position_key')}")
        
        # ==================== Step 4: 启动持仓监控（Gamma Scalping）====================
        print(f"\n{'='*70}")
        print(f"🛡️  启动 RiskManager 持仓监控（Gamma Scalping 模式）")
        print(f"{'='*70}")
        print(f"   监控功能:")
        print(f"   ✅ 实时 P&L 监控")
        print(f"   ✅ 止损/止盈检查 (SL: {risk_manager.stop_loss_ratio:.1%}, TP: {risk_manager.profit_target_ratio:.1%})")
        print(f"   ✅ IV 反转监控")
        print(f"   🔥 Delta 对冲（Gamma Scalping）：阈值 {risk_manager.delta_hedge_threshold}")
        print(f"   📊 对冲频率：每 {risk_manager.hedge_freq} 个监控周期（约 {risk_manager.hedge_freq * 0.5:.0f} 分钟）")
        print(f"\n⏳ 进入监控循环（持仓平仓后自动退出）...\n")
        
        # 直接调用监控（阻塞直到持仓平仓）
        try:
            risk_manager.monitor_positions(check_duration="1min")
        except Exception as e:
            print(f"\n❌ 监控异常: {e}")
            import traceback
            traceback.print_exc()
        
        print(f"\n✅ 持仓监控已退出，持仓已全部平仓！")
        
        # ==================== Step 5: 显示最终统计 ====================
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        options_pnl = risk_manager.total_options_realized_pnl
        perp_pnl = risk_manager.total_perp_realized_pnl if risk_manager.enable_delta_hedge else 0.0
        total_pnl = options_pnl + perp_pnl
        
        print(f"\n{'='*70}")
        print(f"📊 Gamma Scalping 交易最终统计")
        print(f"{'='*70}")
        print(f"⏱️  总耗时: {total_duration / 60:.1f} 分钟")
        print(f"📅 开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📅 结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\n💰 P&L 汇总:")
        print(f"   期权已实现 P&L: {options_pnl:+.8f} ETH")
        if risk_manager.enable_delta_hedge:
            print(f"   永续已实现 P&L (Gamma Scalping): {perp_pnl:+.8f} ETH")
        print(f"   总已实现 P&L: {total_pnl:+.8f} ETH")
        
        # 计算收益率
        estimated_cost = opportunity.total_premium * crypto_notional  # Selling Straddle 收取的权利金
        if estimated_cost > 0:
            roi = (total_pnl / estimated_cost) * 100
            print(f"   收取权利金: {estimated_cost:.8f} ETH")
            print(f"   投资回报率: {roi:+.2f}%")
        
        # Gamma Scalping 特有统计
        if risk_manager.enable_delta_hedge and perp_pnl != 0:
            print(f"\n🔥 Gamma Scalping 统计:")
            print(f"   Delta对冲盈亏: {perp_pnl:+.8f} ETH")
            print(f"   期权时间价值衰减: {options_pnl:+.8f} ETH")
        
        print(f"{'='*70}")
        print(f"✅ Gamma Scalping 测试完成！策略验证 {'成功 ✓' if total_pnl > 0 else '需优化 ⚠️'}")
        print(f"{'='*70}\n")
        
    else:
        print(f"\n❌ 交易执行失败: {result.get('error')}")
        print(f"   请检查日志并重试\n")

