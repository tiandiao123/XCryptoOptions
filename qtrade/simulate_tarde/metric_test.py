import numpy as np
import matplotlib.pyplot as plt
import os
from datetime import datetime

def calculate_performance_metrics(time_list, asset_pnl_list, initial_asset, save_folder=None):
    """
    计算核心回测性能指标 - 简洁版 + MDD画图
    
    Args:
        time_list: 时间序列
        asset_pnl_list: 资产价值序列  
        initial_asset: 初始资产
        save_folder: 保存文件夹路径（可选）
        
    Returns:
        dict: 性能指标字典
    """
    if len(asset_pnl_list) < 2:
        return {}
    
    asset_values = np.array(asset_pnl_list)
    returns = np.diff(asset_values) / asset_values[:-1]
    
    # 时间相关
    total_days = (time_list[-1] - time_list[0]).days
    time_years = total_days / 365.25
    
    # 收益指标
    total_return = (asset_values[-1] - initial_asset) / initial_asset
    annualized_return = (1 + total_return) ** (1 / time_years) - 1 if time_years > 0 else 0
    
    # 风险指标
    volatility_30min = np.std(returns, ddof=1) if len(returns) > 1 else 0
    annualized_volatility = volatility_30min * np.sqrt(17532)  # 年化因子: 365.25*24*2
    
    # 核心比率
    sharpe_ratio = annualized_return / annualized_volatility if annualized_volatility > 0 else 0
    
    # 最大回撤计算
    running_max = np.maximum.accumulate(asset_values)
    drawdown_series = (asset_values - running_max) / running_max
    max_drawdown = np.min(drawdown_series)
    
    # 回撤详情
    mdd_end_idx = np.argmin(drawdown_series)
    mdd_start_idx = np.argmax(running_max[:mdd_end_idx+1])
    mdd_duration_days = (time_list[mdd_end_idx] - time_list[mdd_start_idx]).days
    
    # 其他有用指标
    calmar_ratio = annualized_return / abs(max_drawdown) if abs(max_drawdown) > 0 else 0
    
    # Sortino比率 (下行风险调整收益)
    negative_returns = returns[returns < 0]
    downside_volatility = np.std(negative_returns, ddof=1) * np.sqrt(17532) if len(negative_returns) > 1 else 0
    sortino_ratio = annualized_return / downside_volatility if downside_volatility > 0 else 0
    
    # 胜率相关 (基于日收益)
    daily_returns = []
    for i in range(0, len(returns), 48):  # 每48个30分钟点 = 1天
        if i + 48 <= len(returns):
            daily_ret = np.sum(returns[i:i+48])
            daily_returns.append(daily_ret)
    
    win_rate = len([r for r in daily_returns if r > 0]) / len(daily_returns) if daily_returns else 0
    
    # 回撤恢复时间
    recovery_days = 0
    if mdd_end_idx < len(asset_values) - 1:
        peak_value = running_max[mdd_end_idx]
        for i in range(mdd_end_idx, len(asset_values)):
            if asset_values[i] >= peak_value:
                recovery_days = (time_list[i] - time_list[mdd_end_idx]).days
                break
    
    # 🆕 绘制MDD图表
    if save_folder:
        _plot_mdd_analysis(time_list, asset_values, running_max, drawdown_series, 
                          initial_asset, max_drawdown, mdd_start_idx, mdd_end_idx, save_folder)
    
    return {
        'total_return': total_return,
        'annualized_return': annualized_return,
        'annualized_volatility': annualized_volatility,
        'sharpe_ratio': sharpe_ratio,
        'sortino_ratio': sortino_ratio,
        'calmar_ratio': calmar_ratio,
        'max_drawdown': max_drawdown,
        'mdd_start_time': time_list[mdd_start_idx],
        'mdd_end_time': time_list[mdd_end_idx],
        'mdd_duration_days': mdd_duration_days,
        'recovery_days': recovery_days,
        'win_rate': win_rate,
        'time_years': time_years,
        'total_days': total_days
    }


def _plot_mdd_analysis(time_list, asset_values, running_max, drawdown_series, 
                      initial_asset, max_drawdown, mdd_start_idx, mdd_end_idx, save_folder):
    """绘制MDD分析图表 - 内部函数"""
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    
    # 上图：资产价值 vs 峰值
    ax1.plot(time_list, asset_values, 'b-', linewidth=2, label='Asset Value', alpha=0.8)
    ax1.plot(time_list, running_max, 'g--', linewidth=1.5, label='Peak Value', alpha=0.7)
    ax1.axhline(y=initial_asset, color='gray', linestyle=':', alpha=0.5, label=f'Initial: {initial_asset:.4f}')
    ax1.set_ylabel('Asset (BTC)')
    ax1.set_title('Maximum Drawdown Analysis', fontweight='bold')
    ax1.grid(True, alpha=0.3)
    ax1.legend()
    
    # 标记MDD起止点
    ax1.scatter(time_list[mdd_start_idx], running_max[mdd_start_idx], color='red', s=60, marker='o', zorder=5)
    ax1.scatter(time_list[mdd_end_idx], asset_values[mdd_end_idx], color='red', s=60, marker='v', zorder=5)
    
    # 下图：回撤曲线
    drawdown_pct = drawdown_series * 100
    ax2.fill_between(time_list, drawdown_pct, 0, where=(drawdown_pct < 0), color='red', alpha=0.3)
    ax2.plot(time_list, drawdown_pct, 'r-', linewidth=1.5, alpha=0.8)
    ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax2.set_ylabel('Drawdown (%)')
    ax2.set_xlabel('Time')
    ax2.grid(True, alpha=0.3)
    
    # 标注最大回撤
    max_dd_pct = max_drawdown * 100
    ax2.scatter(time_list[mdd_end_idx], max_dd_pct, color='darkred', s=80, marker='v', zorder=5)
    ax2.text(time_list[mdd_end_idx], max_dd_pct-1, f'MDD: {max_dd_pct:.2f}%', 
             ha='center', va='top', fontsize=10, 
             bbox=dict(boxstyle='round,pad=0.3', facecolor='yellow', alpha=0.7))
    
    # 时间轴格式化
    time_span = (time_list[-1] - time_list[0]).days
    if time_span > 365:
        date_format = '%Y-%m'
    elif time_span > 60:
        date_format = '%m-%d'
    else:
        date_format = '%m-%d %H:%M'
    
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    
    # 保存图表
    mdd_file = os.path.join(save_folder, 'mdd_analysis.png')
    plt.savefig(mdd_file, dpi=300, bbox_inches='tight')
    print(f"📊 MDD图表已保存: {mdd_file}")
    plt.close()
