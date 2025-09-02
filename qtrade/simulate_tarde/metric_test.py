import numpy as np
from datetime import datetime

def calculate_performance_metrics(time_list, asset_pnl_list, initial_asset):
    """
    计算核心回测性能指标 - 简洁版
    
    Args:
        time_list: 时间序列
        asset_pnl_list: 资产价值序列  
        initial_asset: 初始资产
        
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
