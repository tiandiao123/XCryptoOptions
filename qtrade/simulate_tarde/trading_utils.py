import os 
import matplotlib.pyplot as plt
import numpy as np


def option_margin(option_type: str,
                  spot_price: float,
                  strike: float,
                  mark_price: float,
                  contracts: int,
                  multiplier: float = 0.01,
                  margin_factor: float = 1.0):
    """
    计算期权卖方的初始保证金 (IMR) 和维持保证金 (MMR)
    支持 Call 和 Put
    
    Parameters
    ----------
    option_type : str
        "call" 或 "put"
    spot_price : float
        标的价格 (Index/Futures price)
    strike : float
        期权行权价
    mark_price : float
        期权标记价格 (单位 BTC)
    contracts : int
        卖出的合约张数
    multiplier : float
        每张合约乘数 (BTC/张)，OKX 通常是 0.01
    margin_factor : float
        保证金系数（Position Tier 不同会 >1），默认 1.0
    
    Returns
    -------
    (IMR, MMR)
        - IMR: 初始保证金 (BTC)
        - MMR: 维持保证金 (BTC)
    """
    
    # 计算 OTM Value
    if option_type.lower() == "call":
        otm_value = max(0.0, strike - spot_price)
    elif option_type.lower() == "put":
        otm_value = max(0.0, spot_price - strike)
    else:
        raise ValueError("option_type 必须是 'call' 或 'put'")
    
    # 转换成 BTC
    otm_value_btc = otm_value / spot_price if spot_price > 0 else 0.0
    
    # --- 初始保证金 IMR ---
    if option_type.lower() == "call":
        imr_per_contract = (max(0.1, 0.15 - otm_value / spot_price) * margin_factor + mark_price) * multiplier
    else:  # put
        imr_per_contract = (max(0.1 * (1 + mark_price), 0.15 - otm_value / spot_price) * margin_factor + mark_price) * multiplier
    
    IMR = imr_per_contract * contracts
    
    # --- 维持保证金 MMR ---
    if option_type.lower() == "call":
        mmr_per_contract = (0.075 * margin_factor + mark_price) * multiplier
    else:  # put
        mmr_per_contract = (0.075 * (1 + mark_price) * margin_factor + mark_price) * multiplier
    
    MMR = mmr_per_contract * contracts
    
    return IMR, MMR


def print_hedge_stats(hedge_stats, contract_performance_stats, save_folder=None):
    """
    打印并绘制对冲统计和合约胜率统计
    
    Args:
        hedge_stats: 对冲统计字典
        contract_performance_stats: 合约表现统计字典
        save_folder: 保存图表的文件夹路径
    """
    # 🆕 打印对冲统计
    if hedge_stats['hedge_sizes']:
        print(f"\n📊 Delta对冲统计:")
        print(f"   对冲操作次数: {hedge_stats['total_hedge_operations']}")
        print(f"   启用对冲的交易: {hedge_stats['hedge_enabled_trades']}")
        print(f"   最大对冲大小: {hedge_stats['max_hedge_size']:.4f} BTC")
        print(f"   最小对冲大小: {hedge_stats['min_hedge_size']:.4f} BTC")
        print(f"   平均对冲大小: {np.mean(hedge_stats['hedge_sizes']):.4f} BTC")
        print(f"   对冲大小标准差: {np.std(hedge_stats['hedge_sizes']):.4f} BTC")
        
        # 🆕 绘制Delta对冲统计图
        _plot_hedge_statistics(hedge_stats, save_folder)
    else:
        print(f"\n📊 Delta对冲统计: 无对冲操作")
    
    # 🆕 打印合约胜率统计
    if contract_performance_stats['total_contracts'] > 0:
        win_rate = contract_performance_stats['profitable_contracts'] / contract_performance_stats['total_contracts']
        avg_profit = contract_performance_stats['profitable_pnl_sum'] / max(1, contract_performance_stats['profitable_contracts'])
        losing_contracts = contract_performance_stats['total_contracts'] - contract_performance_stats['profitable_contracts']
        avg_loss = contract_performance_stats['losing_pnl_sum'] / max(1, losing_contracts) if losing_contracts > 0 else 0
        
        print(f"\n🎯 合约胜率统计:")
        print(f"   总合约数: {contract_performance_stats['total_contracts']}")
        print(f"   盈利合约数: {contract_performance_stats['profitable_contracts']}")
        print(f"   合约胜率: {win_rate:.2%}")
        print(f"   平均盈利: {avg_profit:.6f} BTC")
        print(f"   平均亏损: {avg_loss:.6f} BTC")
        if avg_loss != 0:
            print(f"   盈亏比: {abs(avg_profit/avg_loss):.2f}")
        else:
            print(f"   盈亏比: N/A (无亏损合约)")
        print(f"   总P&L: {contract_performance_stats['total_pnl_sum']:.6f} BTC")
        
        # 🆕 绘制合约P&L分布图
        _plot_contract_pnl_distribution(contract_performance_stats, save_folder)
    else:
        print(f"\n🎯 合约胜率统计: 无交易合约")


def _plot_hedge_statistics(hedge_stats, save_folder=None):
    """绘制Delta对冲统计图"""
    if not hedge_stats['hedge_sizes']:
        return
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    hedge_sizes = np.array(hedge_stats['hedge_sizes'])
    
    # 1. 对冲大小分布直方图
    ax1.hist(hedge_sizes, bins=20, alpha=0.7, color='orange', edgecolor='black')
    ax1.axvline(np.mean(hedge_sizes), color='red', linestyle='--', 
                label=f'均值: {np.mean(hedge_sizes):.4f}')
    ax1.set_xlabel('Hedge size (BTC)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Delta hedge size distribution')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. 对冲大小时间序列
    ax2.plot(range(len(hedge_sizes)), hedge_sizes, 'o-', alpha=0.7, markersize=3)
    ax2.set_xlabel('Delta hedge operation number')
    ax2.set_ylabel('Delta hedge size (BTC)')
    ax2.set_title('Delta hedge size time series')
    ax2.grid(True, alpha=0.3)
    
    # 3. 对冲大小箱线图
    ax3.boxplot(hedge_sizes, vert=True)
    ax3.set_ylabel('Delta hedge size (BTC)')
    ax3.set_title('Delta hedge size distribution box plot')
    ax3.grid(True, alpha=0.3)
    
    # 4. 统计汇总文本
    ax4.axis('off')
    stats_text = f"""Delta hedge statistics summary
    
total delta hedge operations: {hedge_stats['total_hedge_operations']:,}次
the number of initiating delta hedge for contracts: {hedge_stats['hedge_enabled_trades']:,}笔

Hedge size statistics:
• Maximum: {hedge_stats['max_hedge_size']:.4f} BTC
• Minimum: {hedge_stats['min_hedge_size']:.4f} BTC  
• Mean: {np.mean(hedge_sizes):.4f} BTC
• Median: {np.median(hedge_sizes):.4f} BTC
• Standard deviation: {np.std(hedge_sizes):.4f} BTC

Quartiles:
• 25%: {np.percentile(hedge_sizes, 25):.4f} BTC
• 75%: {np.percentile(hedge_sizes, 75):.4f} BTC
• 95%: {np.percentile(hedge_sizes, 95):.4f} BTC
    """
    
    ax4.text(0.1, 0.9, stats_text, transform=ax4.transAxes, fontsize=11,
             verticalalignment='top', fontfamily='monospace',
             bbox=dict(boxstyle="round,pad=0.5", facecolor='lightgray', alpha=0.8))
    
    plt.tight_layout()
    
    # 保存图表
    if save_folder:
        chart_path = os.path.join(save_folder, 'delta_hedge_statistics.png')
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        print(f"📊 Delta hedge statistics chart saved: {chart_path}")
    
    plt.show()


def _plot_contract_pnl_distribution(contract_stats, save_folder=None):
    """绘制合约P&L分布图"""
    if not contract_stats['contract_pnls']:
        return
    
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))
    pnls = np.array(contract_stats['contract_pnls'])
    
    # 1. P&L分布直方图
    ax1.hist(pnls, bins=20, alpha=0.7, color='steelblue', edgecolor='black')
    ax1.axvline(0, color='red', linestyle='-', alpha=0.7, label='Break even point')
    ax1.axvline(np.mean(pnls), color='orange', linestyle='--', 
                label=f'均值: {np.mean(pnls):.6f}')
    ax1.set_xlabel('P&L (BTC)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Contracts P&L distribution')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # 2. P&L累积分布
    sorted_pnls = np.sort(pnls)
    cumulative_prob = np.arange(1, len(sorted_pnls) + 1) / len(sorted_pnls)
    ax2.plot(sorted_pnls, cumulative_prob, linewidth=2, color='green')
    ax2.axvline(0, color='red', linestyle='--', alpha=0.7, label='Break even point')
    ax2.set_xlabel('P&L (BTC)')
    ax2.set_ylabel('Cumulative probability')
    ax2.set_title('P&L cumulative distribution function')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # 3. 胜率饼图
    profitable_count = contract_stats['profitable_contracts']
    losing_count = contract_stats['total_contracts'] - profitable_count
    
    labels = ['Contracts winning', 'Contracts losing']
    sizes = [profitable_count, losing_count]
    colors = ['lightgreen', 'lightcoral']
    
    ax3.pie(sizes, labels=labels, colors=colors, autopct='%1.1f%%', startangle=90)
    ax3.set_title(f'Contracts win rate distribution\n(Total: {contract_stats["total_contracts"]} contracts)')
    
    # 4. P&L箱线图
    ax4.boxplot(pnls, vert=True)
    ax4.axhline(0, color='red', linestyle='--', alpha=0.7, label='Break even point')
    ax4.set_ylabel('P&L (BTC)')
    ax4.set_title('Contracts P&L distribution box plot')
    ax4.legend()
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # 保存图表
    if save_folder:
        chart_path = os.path.join(save_folder, 'contract_pnl_distribution.png')
        plt.savefig(chart_path, dpi=300, bbox_inches='tight')
        print(f"📊 Contracts P&L distribution chart saved: {chart_path}")
    
    plt.show()

def print_final_backtest_report(
    processed_count,
    opportunities_found,
    unique_dates_with_opportunities,
    unique_dates,
    total_elapsed,
    init_btc,
    sum_asset_pnl,
    trade_quality_stats,
    exclude_abnormal_trades,
    time_list,
    sum_asset_pnl_list,
    save_folder,
    enable_plot=True,
    strategy_name="Spread Strategy"
):
    """
    打印回测的最终统计报告
    
    Args:
        processed_count: 处理的时间点数量
        opportunities_found: 发现的交易机会数量
        unique_dates_with_opportunities: 有机会的唯一日期集合
        unique_dates: 所有唯一日期集合
        total_elapsed: 总耗时（秒）
        init_btc: 初始BTC资产
        sum_asset_pnl: 最终资产P&L
        trade_quality_stats: 交易质量统计字典
        exclude_abnormal_trades: 是否排除异常交易
        time_list: 时间列表
        sum_asset_pnl_list: 资产P&L列表
        save_folder: 保存文件夹
        enable_plot: 是否启用图表
        strategy_name: 策略名称
    
    Returns:
        dict: 性能指标字典
    """
    from qtrade.simulate_tarde.metric_performance import calculate_performance_metrics
    
    # 计算基础统计
    unique_dates_count = len(unique_dates_with_opportunities)
    total_unique_dates = len(unique_dates)
    final_return = (sum_asset_pnl - init_btc) / init_btc * 100
    
    # 打印基础统计
    print(f"\n" + "="*60)
    print(f"🎉 {strategy_name}回测完成！")
    print(f"="*60)
    print(f"📊 基础统计:")
    print(f"   总时间点: {processed_count:,}")
    print(f"   交易机会: {opportunities_found:,}")
    print(f"   机会比例: {opportunities_found/processed_count*100:.3f}%")
    print(f"   有机会天数: {unique_dates_count:,}/{total_unique_dates:,}")
    print(f"   天数比例: {unique_dates_count/total_unique_dates*100:.2f}%")
    print(f"   用时: {total_elapsed/60:.1f}分钟")
    
    # 打印最终结果
    print(f"\n💰 最终结果:")
    print(f"   初始资产: {init_btc:.6f} BTC")
    print(f"   最终资产: {sum_asset_pnl:.6f} BTC")
    print(f"   总收益: {sum_asset_pnl - init_btc:+.6f} BTC")
    print(f"   总收益率: {final_return:+.2f}%")
    print(f"="*60)
    
    # 交易质量报告
    if exclude_abnormal_trades:
        exclude_rate = trade_quality_stats['excluded_trades'] / max(trade_quality_stats['total_trades'], 1) * 100
        
        print(f"\n📊 交易质量报告:")
        print(f"   总交易数: {trade_quality_stats['total_trades']:,}")
        print(f"   排除交易数: {trade_quality_stats['excluded_trades']:,} ({exclude_rate:.1f}%)")
        print(f"   有效交易率: {100-exclude_rate:.1f}%")
        print(f"   被排除P&L总和: {trade_quality_stats['excluded_pnl_sum']:+.6f} BTC")
        
        if trade_quality_stats['excluded_reasons']:
            print(f"   排除原因统计:")
            for reason, count in trade_quality_stats['excluded_reasons'].items():
                print(f"     {reason}: {count:,}次")
    
    # 保持图表显示
    if enable_plot:
        plt.ioff()
        plt.show()
    
    # 性能指标
    print(f"\n📊 性能指标:")
    metrics = calculate_performance_metrics(time_list, sum_asset_pnl_list, init_btc, save_folder=save_folder)
    if metrics:
        print(f"   年化收益率: {metrics['annualized_return']*100:+.2f}%")
        print(f"   年化波动率: {metrics['annualized_volatility']*100:.2f}%") 
        print(f"   Sharpe比率: {metrics['sharpe_ratio']:.3f}")
        print(f"   Sortino比率: {metrics['sortino_ratio']:.3f}")
        print(f"   最大回撤: {metrics['max_drawdown']*100:.2f}%")
        print(f"   Calmar比率: {metrics['calmar_ratio']:.3f}")
        print(f"   日胜率: {metrics['win_rate']*100:.1f}%")
    
    return metrics

