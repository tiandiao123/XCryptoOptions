from qtrade.simulate_tarde.spread_trading import backtest_strategy
# 📊 Import performance analysis functions
import numpy as np
import os
from datetime import datetime

def _plot_weighted_strategy_analysis(time_list, strategy_data, save_folder='.'):
    """绘制加权策略分析图表"""
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    # 左上图：策略P&L对比
    ax1.plot(time_list, strategy_data['Calendar + Straggle'], 'b-', linewidth=2, 
            label='Calendar + Straggle', alpha=0.8)
    ax1.plot(time_list, strategy_data['Traditional Straddle'], 'r-', linewidth=2, 
            label='Traditional Straddle', alpha=0.8)
    ax1.plot(time_list, strategy_data['Weighted Combination'], 'g-', linewidth=3, 
            label='Weighted Combination', alpha=0.9)
    ax1.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5, label='Initial: 1.0 BTC')
    ax1.set_ylabel('Cumulative P&L (BTC)')
    ax1.set_title('Strategy Performance Comparison', fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # 右上图：加权策略MDD分析
    weighted_pnl = np.array(strategy_data['Weighted Combination'])
    running_max = np.maximum.accumulate(weighted_pnl)
    drawdown_series = (weighted_pnl - running_max) / running_max
    max_drawdown = np.min(drawdown_series)
    mdd_end_idx = np.argmin(drawdown_series)
    mdd_start_idx = np.argmax(running_max[:mdd_end_idx+1])
    
    ax2.plot(time_list, weighted_pnl, 'g-', linewidth=2, label='Weighted P&L', alpha=0.8)
    ax2.plot(time_list, running_max, 'b--', linewidth=1.5, label='Peak Value', alpha=0.7)
    ax2.axhline(y=1.0, color='gray', linestyle=':', alpha=0.5, label='Initial: 1.0 BTC')
    ax2.scatter(time_list[mdd_start_idx], running_max[mdd_start_idx], color='red', s=60, marker='o', zorder=5)
    ax2.scatter(time_list[mdd_end_idx], weighted_pnl[mdd_end_idx], color='red', s=60, marker='v', zorder=5)
    ax2.set_ylabel('Asset Value (BTC)')
    ax2.set_title('Weighted Strategy - Peak & Drawdown', fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.legend()
    
    # 左下图：回撤曲线
    drawdown_pct = drawdown_series * 100
    ax3.fill_between(time_list, drawdown_pct, 0, where=(drawdown_pct < 0), color='red', alpha=0.3)
    ax3.plot(time_list, drawdown_pct, 'r-', linewidth=1.5, alpha=0.8)
    ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    max_dd_pct = max_drawdown * 100
    ax3.scatter(time_list[mdd_end_idx], max_dd_pct, color='darkred', s=80, marker='v', zorder=5)
    ax3.text(time_list[mdd_end_idx], max_dd_pct-0.5, f'MDD: {max_dd_pct:.2f}%', 
            ha='center', va='top', fontsize=10, 
            bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    ax3.set_ylabel('Drawdown (%)')
    ax3.set_title('Weighted Strategy - Drawdown Analysis', fontweight='bold')
    ax3.grid(True, alpha=0.3)
    
    # 右下图：滚动收益率分布
    weighted_returns = np.diff(weighted_pnl)
    ax4.hist(weighted_returns, bins=50, alpha=0.7, color='green', edgecolor='black')
    ax4.axvline(x=np.mean(weighted_returns), color='red', linestyle='--', linewidth=2, 
                label=f'Mean: {np.mean(weighted_returns):.6f}')
    ax4.axvline(x=0, color='black', linestyle='-', linewidth=1, alpha=0.5)
    ax4.set_xlabel('Period Returns (BTC)')
    ax4.set_ylabel('Frequency')
    ax4.set_title('Weighted Strategy - Return Distribution', fontweight='bold')
    ax4.grid(True, alpha=0.3)
    ax4.legend()
    
    # 时间轴格式化
    for ax in [ax1, ax2, ax3]:
        time_span = (time_list[-1] - time_list[0]).days
        if time_span > 365:
            date_format = '%Y-%m'
        elif time_span > 60:
            date_format = '%m-%d'
        else:
            date_format = '%m-%d %H:%M'
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # 保存图表
    analysis_file = os.path.join(save_folder, 'weighted_strategy_analysis.png')
    plt.savefig(analysis_file, dpi=300, bbox_inches='tight')
    print(f"📊 加权策略分析图表已保存: {analysis_file}")
    plt.show()
    
    return max_drawdown, mdd_start_idx, mdd_end_idx

def calculate_strategy_metrics(pnl_series, strategy_name):
    """计算单个策略的性能指标"""
    if len(pnl_series) < 2:
        return {}
    
    returns = np.diff(pnl_series)
    
    # 基础指标
    total_return = pnl_series[-1] - 1.0  # 假设初始资产为1.0
    volatility = np.std(returns)
    sharpe_ratio = np.mean(returns) / volatility * np.sqrt(17532) if volatility > 0 else 0  # 年化
    
    # 最大回撤
    running_max = np.maximum.accumulate(pnl_series)
    drawdown = (pnl_series - running_max) / running_max
    max_drawdown = abs(np.min(drawdown))
    
    # 胜率
    win_rate = np.sum(returns > 0) / len(returns) * 100
    
    return {
        'strategy': strategy_name,
        'total_return': total_return,
        'sharpe_ratio': sharpe_ratio,
        'max_drawdown': max_drawdown,
        'volatility': volatility,
        'win_rate': win_rate,
        'final_value': pnl_series[-1]
    }
    


if __name__ == "__main__":
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    
    strategy_set = set([
        "calendar_spread",
        "gamma_scalping_sell_straddle",
        "gamma_scalping_sell_calendar_spread",
    ])

    strategy_name_1 = "calendar_spread"

    assert strategy_name_1 in strategy_set, f"策略名称 {strategy_name_1} 不在策略集合中"
    
    # 🚀 运行Calendar Spread回测
    time_list_1, sum_asset_pnl_list_1 = backtest_strategy(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,
        plot_update_interval=500,
        exclude_abnormal_trades=True,
        save_folder='calendar_spread_results_strategy_1',

        # 🆕 Delta对冲参数
        enable_delta_hedge=True,  # 启用Delta对冲
        delta_threshold=0.05,     # 5% Delta阈值, once exceed, hedge 
        hedge_cost_bps=0.0000,   # 2bps手续费
        inverse_contract_multiplier=1.0, 
        strategy_name=strategy_name_1,
        use_straggle_search=True, 
        price_pct_threshold=0.01, 

        # risk control parameters
        max_loss_pct=0.3,
        target_profit_pct=0.5,
        max_delta_threshold = 0.4, # close when combined delta exceed this threshold
    )



    strategy_name_2 = "gamma_scalping_sell_straddle"

    assert strategy_name_2 in strategy_set, f"策略名称 {strategy_name_2} 不在策略集合中"
    
    time_list_2, sum_asset_pnl_list_2 = backtest_strategy(
        data_folder=data_folder, 
        init_btc=1.0,
        enable_plot=True,
        plot_update_interval=500,
        exclude_abnormal_trades=True,
        save_folder='gamma_scalping_sell_straddle_results_strategy_2',

        # 🆕 Delta对冲参数
        enable_delta_hedge=True,  # 启用Delta对冲
        delta_threshold=0.05,     # 5% Delta阈值, once exceed, hedge 
        hedge_cost_bps=0.0000,   # 2bps手续费
        inverse_contract_multiplier=1.0, 
        strategy_name=strategy_name_2,
        use_straggle_search=False,  
        price_pct_threshold=0.01, 

        # risk control parameters
        max_loss_pct=0.3,
        target_profit_pct=0.5,
        max_delta_threshold = 0.4, # close when combined delta exceed this threshold
    )


    assert len(time_list_1) == len(time_list_2), "time_list_1 和 time_list_2 长度不一致"

    assert len(sum_asset_pnl_list_1) == len(sum_asset_pnl_list_2), "sum_asset_pnl_list_1 和 sum_asset_pnl_list_2 长度不一致"

    # Complete the weighted combination
    import numpy as np
    import matplotlib.pyplot as plt

    # Calculate weighted average (equal weights)
    weighted_pnl = [(pnl1 + pnl2) / 2 for pnl1, pnl2 in zip(sum_asset_pnl_list_1, sum_asset_pnl_list_2)]

    # Plot comparison
    plt.figure(figsize=(12, 8))
    plt.plot(time_list_1, sum_asset_pnl_list_1, label='Calendar + Straggle', alpha=0.7)
    plt.plot(time_list_2, sum_asset_pnl_list_2, label='Traditional Straddle', alpha=0.7)
    plt.plot(time_list_1, weighted_pnl, label='Weighted Combination', linewidth=2)
    plt.xlabel('Time')
    plt.ylabel('Cumulative P&L (BTC)')
    plt.title('Strategy Performance Comparison')
    plt.legend()
    plt.grid(True)

    plt.savefig('weighted_com_spread_trading_result.png')
    plt.show()
    
    # 准备策略数据
    strategy_data = {
        'Calendar + Straggle': sum_asset_pnl_list_1,
        'Traditional Straddle': sum_asset_pnl_list_2,
        'Weighted Combination': weighted_pnl
    }
    
    # 创建保存文件夹
    save_folder = 'weighted_strategy_results'
    os.makedirs(save_folder, exist_ok=True)
    
    # 绘制分析图表
    max_dd, mdd_start, mdd_end = _plot_weighted_strategy_analysis(time_list_1, strategy_data, save_folder)
    
    # 计算并打印性能指标
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE STRATEGY PERFORMANCE ANALYSIS")
    print("="*80)
    
    for strategy_name, pnl_series in strategy_data.items():
        metrics = calculate_strategy_metrics(pnl_series, strategy_name)
        
        print(f"\n🎯 {strategy_name}:")
        print(f"   Final Value:      {metrics['final_value']:+.6f} BTC")
        print(f"   Total Return:     {metrics['total_return']:+.4f} BTC ({metrics['total_return']*100:+.2f}%)")
        print(f"   Sharpe Ratio:     {metrics['sharpe_ratio']:+.4f}")
        print(f"   Max Drawdown:     {metrics['max_drawdown']:.4f} ({metrics['max_drawdown']*100:.2f}%)")
        print(f"   Volatility:       {metrics['volatility']:.6f}")
        print(f"   Win Rate:         {metrics['win_rate']:.2f}%")
    
    # 加权策略特殊分析
    weighted_returns = np.diff(weighted_pnl)
    print(f"\n📈 WEIGHTED COMBINATION DETAILED METRICS:")
    print(f"   Best Period:      {np.max(weighted_returns):+.6f} BTC")
    print(f"   Worst Period:     {np.min(weighted_returns):+.6f} BTC")
    print(f"   Avg Period P&L:   {np.mean(weighted_returns):+.6f} BTC")
    print(f"   MDD Duration:     {(time_list_1[mdd_end] - time_list_1[mdd_start]).days} days")
    print(f"   Recovery Status:  {'✅ Recovered' if weighted_pnl[-1] >= np.max(weighted_pnl[:mdd_end]) else '⚠️ Not Recovered'}")
    
    print("\n" + "="*80)