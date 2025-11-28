#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gamma Scalping - Selling Straddle 多次交易测试
循环执行：寻找机会 → 开仓 → Delta对冲监控 → 平仓 → 重新寻找

核心特性：
1. 自动化循环交易
2. 持续寻找 Selling Straddle 机会
3. Delta 对冲（Gamma Scalping）
4. P&L 追踪和可视化
5. 累积收益统计
"""

import time
import matplotlib.pyplot as plt
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
    # 初始化寻找器
    finder = SellingStraddleFinderOKX(config_path, currency)
    
    # 搜索机会
    opportunities = finder.find_selling_straddle_opportunities()
    
    if not opportunities:
        print("   未找到 Selling Straddle 机会")
        return None
    
    # 显示结果
    if show_details:
        finder.display_opportunities(opportunities, detailed=True)
    
    # 返回最佳机会（已按评分排序）
    best_opportunity = opportunities[0]
    print(f"   Call: {best_opportunity.call_option.symbol}")
    print(f"   Put:  {best_opportunity.put_option.symbol}")
    print(f"   执行价: ${best_opportunity.strike_price:,.0f}")
    print(f"   到期天数: {best_opportunity.days_to_expiry} 天")
    print(f"   IV Premium: {best_opportunity.iv_premium_pct:+.1f}%")
    print(f"   总权利金: {best_opportunity.total_premium:.4f} {currency}")
    
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
        
        # 记录开仓价格（从 result 中获取实际成交价）
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
            
            # 将 result 扩展
            result["risk_manager_added"] = True
            result["position_key"] = position_key
        else:
            print(f"⚠️  加入 RiskManager 失败（持仓已满或已存在）")
            result["risk_manager_added"] = False
    
    return result


def plot_pnl_curve(pnl_history: list, timestamps: list, save_path: str = "/home/ubuntu/options_trading/gamma_scalping_pnl_curve.png"):
    """
    绘制累积 P&L 曲线
    
    Args:
        pnl_history: P&L历史列表 [(trade_num, options_pnl, perp_pnl, total_pnl), ...]
        timestamps: 时间戳列表
        save_path: 保存路径
    """
    if not pnl_history:
        print("⚠️ 没有P&L数据，跳过绘图")
        return
    
    # 提取数据
    trade_nums = [item[0] for item in pnl_history]
    cumulative_options_pnl = []
    cumulative_perp_pnl = []
    cumulative_total_pnl = []
    
    cum_opt = 0.0
    cum_perp = 0.0
    cum_total = 0.0
    
    for _, opt_pnl, perp_pnl, total_pnl in pnl_history:
        cum_opt += opt_pnl
        cum_perp += perp_pnl
        cum_total += total_pnl
        
        cumulative_options_pnl.append(cum_opt)
        cumulative_perp_pnl.append(cum_perp)
        cumulative_total_pnl.append(cum_total)
    
    # 创建图表
    plt.figure(figsize=(14, 8))
    
    # 绘制累积 P&L 曲线
    plt.plot(trade_nums, cumulative_total_pnl, 'b-o', linewidth=2, markersize=8, label='Total Cumulative P&L', alpha=0.8)
    plt.plot(trade_nums, cumulative_options_pnl, 'g--^', linewidth=1.5, markersize=6, label='Options Cumulative P&L', alpha=0.7)
    
    if any(perp != 0 for perp in cumulative_perp_pnl):
        plt.plot(trade_nums, cumulative_perp_pnl, 'r--s', linewidth=1.5, markersize=6, label='Perp Cumulative P&L (Gamma Scalping)', alpha=0.7)
    
    # 添加零线
    plt.axhline(y=0, color='gray', linestyle='--', linewidth=1, alpha=0.5)
    
    # 标注最终 P&L
    final_pnl = cumulative_total_pnl[-1]
    plt.annotate(f'Final: {final_pnl:+.4f} ETH', 
                 xy=(trade_nums[-1], final_pnl),
                 xytext=(10, 10), textcoords='offset points',
                 bbox=dict(boxstyle='round,pad=0.5', fc='yellow', alpha=0.7),
                 arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=0'))
    
    # 图表美化
    plt.xlabel('Trade Number', fontsize=12, fontweight='bold')
    plt.ylabel('Cumulative P&L (ETH)', fontsize=12, fontweight='bold')
    plt.title(f'Gamma Scalping - Selling Straddle Cumulative P&L\nStart: {timestamps[0]} | Latest: {timestamps[-1]}', 
              fontsize=14, fontweight='bold')
    plt.legend(loc='best', fontsize=10)
    plt.grid(True, alpha=0.3, linestyle='--')
    
    # 添加统计信息
    win_count = sum(1 for _, _, _, total in pnl_history if total > 0)
    loss_count = len(pnl_history) - win_count
    win_rate = win_count / len(pnl_history) * 100 if pnl_history else 0
    
    stats_text = f'Total Trades: {len(pnl_history)}\nWins: {win_count} | Losses: {loss_count}\nWin Rate: {win_rate:.1f}%'
    plt.text(0.02, 0.98, stats_text, transform=plt.gca().transAxes, 
             fontsize=10, verticalalignment='top',
             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    print(f"\nP&L curve saved: {save_path}")
    
    plt.close()


if __name__ == "__main__":
    # ==================== 全局配置 ====================
    straddle_config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
    env = "testnet"  # testnet 或 mainnet
    crypto_notional = 0.1  # 每次交易的数量（ETH）
    
    print("\n" + "="*70)
    print("Gamma Scalping - Selling Straddle Auto Trading System")
    print("="*70)
    print(f"   Environment: {'DEMO' if env == 'testnet' else 'LIVE'}")
    print(f"   Notional: {crypto_notional} ETH")
    print(f"   Strategy: Loop (Find -> Open -> Delta Hedge -> Close -> Repeat)")
    print("="*70)
    
    # ==================== Step 1: 初始化 RiskManager ====================
    print(f"\n{'='*70}")
    print(f"Initialize RiskManager (Gamma Scalping Mode)")
    print(f"{'='*70}")
    
    risk_manager = OKXRiskManager(
        symbol="ETHUSD",  # ETH期权
        max_positions=5,
        enable_delta_hedge=True,       # 启用 Delta 对冲（Gamma Scalping）
        delta_hedge_threshold=0.05,    # Delta 阈值：±0.05
        stop_loss_ratio=-0.50,         # -50% 止损（Selling Straddle 风险较大）
        profit_target_ratio=0.30,      # +30% 止盈（收敛策略）
        price_change_risk_ratio=0.15,
        hedge_freq=10,  # 每10个监控周期执行一次对冲检查（约5分钟）
        env=env
    )
    
    print(f"RiskManager initialized")
    print(f"   Max Positions: {risk_manager.max_positions}")
    print(f"   Delta Hedge: ENABLED (Gamma Scalping)")
    print(f"   Delta Threshold: {risk_manager.delta_hedge_threshold}")
    print(f"   Hedge Frequency: Every {risk_manager.hedge_freq} monitor cycles")
    print(f"   Stop Loss: {risk_manager.stop_loss_ratio:.1%}")
    print(f"   Profit Target: {risk_manager.profit_target_ratio:.1%}")
    
    # ==================== Step 2: 主交易循环 ====================
    simulated = (env == "testnet")
    trade_count = 0
    
    # P&L 历史记录
    pnl_history = []  # [(trade_num, options_pnl, perp_pnl, total_pnl), ...]
    timestamps = []   # 每次交易的时间戳
    cumulative_total_pnl = 0.0  # 全局累积 P&L
    
    try:
        while True:
            trade_count += 1
            
            print(f"\n{'='*70}")
            print(f"Trade Cycle #{trade_count}")
            print(f"{'='*70}")
            
            # Step 2.1: 重置 Realized P&L（开始新的交易周期）
            print(f"\nResetting P&L tracker...")
            risk_manager.total_options_realized_pnl = 0.0
            risk_manager.total_perp_realized_pnl = 0.0
            risk_manager.perp_pnl_dict.clear()
            risk_manager.last_perp_fill_time = None
            # 重置 RiskManager 启动时间（作为本轮 P&L 统计起点）
            risk_manager.risk_manager_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"P&L reset complete")
            print(f"   P&L tracking start: {risk_manager.risk_manager_start_time}")
            
            # Step 2.2: 寻找交易机会
            print(f"\nSearching for Selling Straddle opportunities...")
            opportunity = None
            search_attempts = 0
            
            while opportunity is None:
                search_attempts += 1
                print(f"   Attempt #{search_attempts}...")
                
                opportunity = get_selling_straddle_opportunity(
                    config_path=straddle_config_path,
                    currency="ETH",
                    show_details=False
                )
                
                if opportunity:
                    print(f"\nOpportunity found!")
                    break
                else:
                    print(f"   No opportunity, waiting 30s...")
                    time.sleep(30)
            
            # Step 2.3: 执行交易
            print(f"\nTrade execution parameters:")
            print(f"   Currency: ETH")
            print(f"   Notional: {crypto_notional} ETH")
            print(f"   Environment: {'DEMO' if simulated else 'LIVE'}")
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
                print(f"Trade #{trade_count} executed successfully!")
                print(f"{'='*70}")
                print(f"   Execution time: {result['total_time']:.2f}s")
                print(f"   Winner leg: {result['winner'].upper()}")
                print(f"   Position Key: {result.get('position_key')}")
                
                # Step 2.4: 启动持仓监控（Gamma Scalping）
                print(f"\n{'='*70}")
                print(f"Starting RiskManager monitoring (Gamma Scalping Mode)")
                print(f"{'='*70}")
                print(f"   Monitoring features:")
                print(f"   - Real-time P&L tracking")
                print(f"   - Stop Loss/Take Profit (SL: {risk_manager.stop_loss_ratio:.1%}, TP: {risk_manager.profit_target_ratio:.1%})")
                print(f"   - IV reversal monitoring")
                print(f"   - Delta hedging (Gamma Scalping): threshold {risk_manager.delta_hedge_threshold}")
                print(f"\nEntering monitoring loop (will exit after position close)...\n")
                
                # 直接调用监控（阻塞直到持仓平仓）
                try:
                    risk_manager.monitor_positions(check_duration="1min")
                except Exception as e:
                    print(f"\nMonitoring error: {e}")
                    import traceback
                    traceback.print_exc()
                
                print(f"\nMonitoring exited, position closed!")
                
                # Step 2.6: 记录 P&L 到历史
                options_pnl = risk_manager.total_options_realized_pnl
                perp_pnl = risk_manager.total_perp_realized_pnl if risk_manager.enable_delta_hedge else 0.0
                round_total_pnl = options_pnl + perp_pnl
                
                cumulative_total_pnl += round_total_pnl
                
                pnl_history.append((trade_count, options_pnl, perp_pnl, round_total_pnl))
                timestamps.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                
                print(f"\nTrade #{trade_count} P&L Summary:")
                print(f"   Options Realized P&L: {options_pnl:+.8f} ETH")
                if risk_manager.enable_delta_hedge:
                    print(f"   Perp Realized P&L (Gamma Scalping): {perp_pnl:+.8f} ETH")
                print(f"   Round Total P&L: {round_total_pnl:+.8f} ETH")
                print(f"   Cumulative Total P&L: {cumulative_total_pnl:+.8f} ETH")
                
                # Step 2.7: 绘制 P&L 曲线
                plot_pnl_curve(pnl_history, timestamps)
                
                # Step 2.8: 准备下一轮
                print(f"\nTrade cycle #{trade_count} completed, preparing for next round...")
                print(f"   Waiting 10s before searching for new opportunity...")
                time.sleep(10)
                
            else:
                print(f"\nTrade #{trade_count} execution failed: {result.get('error')}")
                print(f"   Waiting 60s before retry...")
                time.sleep(60)
                
    except KeyboardInterrupt:
        print(f"\n\nUser interrupted, exiting trading loop")
        print(f"   Total completed trade cycles: {len(pnl_history)}")
        
        if pnl_history:
            print(f"\nFinal Statistics:")
            print(f"   Cumulative Total P&L: {cumulative_total_pnl:+.8f} ETH")
            print(f"   Winning trades: {sum(1 for _, _, _, total in pnl_history if total > 0)}")
            print(f"   Losing trades: {sum(1 for _, _, _, total in pnl_history if total < 0)}")
            
            # 保存最终 P&L 曲线
            print(f"\nGenerating final P&L curve...")
            plot_pnl_curve(pnl_history, timestamps)

