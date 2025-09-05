import os 
import matplotlib.pyplot as plt


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

