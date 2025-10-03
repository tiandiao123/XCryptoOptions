# -*- coding: utf-8 -*-
"""
波动率跟踪器 - 实时波动率预测
支持 EWMA 和 GARCH 模型
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from collections import deque
import warnings
from typing import Optional, Tuple, List, Dict

class VolTracker:
    """
    波动率跟踪器类 - 用于实时波动率预测
    
    功能:
    1. EWMA (指数加权移动平均) 波动率预测
    2. GARCH 模型波动率预测 (可选)
    3. 滚动窗口价格数据管理
    4. 实时更新机制
    """
    
    def __init__(self, 
                 window_size: int = 96,  # 2天的30分钟数据 (48*2)
                 ewma_lambda: float = 0.94,  # EWMA衰减因子
                 min_periods: int = 20,  # 最小计算周期
                 refit_frequency: int = 48,  # 重新拟合频率(每天)
                 annualization_factor: float = 17520):  # 年化因子 (365*24*2 for 30min)
        """
        初始化波动率跟踪器
        
        Args:
            window_size: 滚动窗口大小 (数据点数)
            ewma_lambda: EWMA衰减因子 (0-1, 越大越平滑)
            min_periods: 开始计算的最小数据点数
            refit_frequency: 重新拟合GARCH模型的频率
            annualization_factor: 年化因子
        """
        self.window_size = window_size
        self.ewma_lambda = ewma_lambda
        self.min_periods = min_periods
        self.refit_frequency = refit_frequency
        self.annualization_factor = annualization_factor
        
        # 数据存储
        self.prices = deque(maxlen=window_size)
        self.returns = deque(maxlen=window_size-1)
        self.timestamps = deque(maxlen=window_size)
        
        # 波动率预测
        self.current_ewma_vol = None
        self.current_garch_vol = None
        self.ewma_variance = None
        
        # 统计信息
        self.update_count = 0
        self.last_refit_time = None
        self.garch_model = None
        self.garch_available = False
        
        # 尝试导入GARCH相关库
        try:
            from arch import arch_model
            self.garch_available = True
            print("✅ GARCH模型可用 (arch库已安装)")
        except ImportError:
            print("⚠️  GARCH模型不可用 (需要安装: pip install arch)")
    
    def add_price(self, price: float, timestamp: datetime) -> Dict:
        """
        添加新的价格数据点并更新波动率预测
        
        Args:
            price: 现货价格
            timestamp: 时间戳
            
        Returns:
            dict: 更新结果，包含预测的波动率
        """
        self.prices.append(price)
        self.timestamps.append(timestamp)
        self.update_count += 1
        
        # 计算收益率
        if len(self.prices) >= 2:
            ret = np.log(price / self.prices[-2])
            self.returns.append(ret)
        
        # 更新波动率预测
        result = self._update_volatility_forecasts()
        
        # 检查是否需要重新拟合GARCH模型
        if self._should_refit_garch():
            self._refit_garch_model()
        
        return result
    
    def _update_volatility_forecasts(self) -> Dict:
        """更新波动率预测"""
        result = {
            'timestamp': self.timestamps[-1] if self.timestamps else None,
            'price': self.prices[-1] if self.prices else None,
            'ewma_vol_30min': None,
            'ewma_vol_annualized': None,
            'garch_vol_30min': None,
            'garch_vol_annualized': None,
            'data_points': len(self.prices),
            'returns_count': len(self.returns)
        }
        
        if len(self.returns) < self.min_periods:
            return result
        
        # 1. 更新EWMA波动率
        self._update_ewma_volatility()
        if self.current_ewma_vol is not None:
            result['ewma_vol_30min'] = self.current_ewma_vol
            result['ewma_vol_annualized'] = self.current_ewma_vol * np.sqrt(self.annualization_factor)
        
        # 2. 更新GARCH波动率 (如果可用)
        if self.garch_available and len(self.returns) >= 50:  # GARCH需要更多数据
            garch_vol = self._predict_garch_volatility()
            if garch_vol is not None:
                result['garch_vol_30min'] = garch_vol
                result['garch_vol_annualized'] = garch_vol * np.sqrt(self.annualization_factor)
        
        return result
    
    def _update_ewma_volatility(self):
        """更新EWMA波动率"""
        returns_array = np.array(self.returns)
        
        if self.ewma_variance is None:
            # 初始化：使用样本方差
            self.ewma_variance = np.var(returns_array, ddof=1)
        else:
            # 递推更新 EWMA
            latest_return = returns_array[-1]
            self.ewma_variance = (
                self.ewma_lambda * self.ewma_variance + 
                (1 - self.ewma_lambda) * latest_return**2
            )
        
        self.current_ewma_vol = np.sqrt(self.ewma_variance)
    
    def _refit_garch_model(self):
        """重新拟合GARCH模型"""
        if not self.garch_available or len(self.returns) < 50:
            return
        
        try:
            from arch import arch_model
            
            # 🔧 修复：不要乘以100，直接使用原始收益率
            returns_array = np.array(self.returns)
            
            # 添加数据验证
            if np.any(np.isnan(returns_array)) or np.any(np.isinf(returns_array)):
                print(f"⚠️  GARCH数据包含异常值，跳过拟合")
                return
            
            # 检查收益率的合理范围
            if np.std(returns_array) > 0.5:  # 如果标准差超过50%，可能有问题
                print(f"⚠️  收益率波动过大 (std: {np.std(returns_array):.3f})，跳过GARCH拟合")
                return
            
            # 拟合GARCH(1,1)模型
            model = arch_model(returns_array, 
                             vol='Garch', 
                             p=1, q=1, 
                             dist='normal',
                             mean='Zero')  # 🔧 添加mean='Zero'简化模型
            
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fitted_model = model.fit(disp='off', show_warning=False, last_obs=min(len(returns_array), 500))
            
            self.garch_model = fitted_model
            self.last_refit_time = self.update_count
            
            # 🔧 添加调试信息
            # print(f"✅ GARCH模型重新拟合完成 (数据点: {len(self.returns)}, 最新收益率标准差: {np.std(returns_array):.4f})")
            
        except Exception as e:
            print(f"❌ GARCH模型拟合失败: {e}")
            # 清理失败的模型
            self.garch_model = None
    
    def _predict_garch_volatility(self) -> Optional[float]:
        """预测GARCH波动率"""
        if not self.garch_available or self.garch_model is None:
            return None
        
        try:
            # 使用当前模型预测下一期波动率
            forecasts = self.garch_model.forecast(horizon=1)
            next_period_variance = forecasts.variance.iloc[-1, 0]
            
            # 🔧 修复：确保方差是合理的
            if next_period_variance <= 0 or np.isnan(next_period_variance) or np.isinf(next_period_variance):
                print(f"⚠️  GARCH预测方差异常: {next_period_variance}")
                return None
            
            # 🔧 修复：限制预测的波动率范围
            predicted_vol = np.sqrt(next_period_variance)
            
            # 合理性检查：年化波动率应该在0.01%-1000%之间
            if predicted_vol < 0.0001 or predicted_vol > 10:
                print(f"⚠️  GARCH预测波动率超出合理范围: {predicted_vol:.4f}")
                return None
                
            return predicted_vol
            
        except Exception as e:
            print(f"⚠️  GARCH预测失败: {e}")
            return None
    
    def _should_refit_garch(self) -> bool:
        """判断是否需要重新拟合GARCH模型"""
        if not self.garch_available:
            return False
        
        # 第一次拟合
        if self.garch_model is None and len(self.returns) >= 100:
            return True
        
        # 定期重新拟合
        if (self.last_refit_time is not None and 
            self.update_count - self.last_refit_time >= self.refit_frequency):
            return True
        
        return False
    
    def get_current_forecast(self) -> Dict:
        """获取当前波动率预测"""
        if len(self.returns) < self.min_periods:
            return {
                'status': 'insufficient_data',
                'data_points': len(self.prices),
                'min_required': self.min_periods
            }
        
        result = {
            'status': 'ready',
            'timestamp': self.timestamps[-1] if self.timestamps else None,
            'current_price': self.prices[-1] if self.prices else None,
            'data_points': len(self.prices),
            'models': {}
        }
        
        # EWMA预测
        if self.current_ewma_vol is not None:
            result['models']['ewma'] = {
                'vol_30min': self.current_ewma_vol,
                'vol_daily': self.current_ewma_vol * np.sqrt(48),  # 48个30分钟
                'vol_annualized': self.current_ewma_vol * np.sqrt(self.annualization_factor),
                'lambda': self.ewma_lambda
            }
        
        # GARCH预测
        garch_vol = self._predict_garch_volatility()
        if garch_vol is not None:
            result['models']['garch'] = {
                'vol_30min': garch_vol,
                'vol_daily': garch_vol * np.sqrt(48),
                'vol_annualized': garch_vol * np.sqrt(self.annualization_factor),
                'last_refit': self.last_refit_time
            }
        
        return result
    
    def get_historical_volatility(self, periods: int = 48) -> Optional[float]:
        """计算历史波动率 (简单标准差方法)"""
        if len(self.returns) < periods:
            return None
        
        recent_returns = list(self.returns)[-periods:]
        return np.std(recent_returns, ddof=1) * np.sqrt(self.annualization_factor)
    
    def reset(self):
        """重置跟踪器"""
        self.prices.clear()
        self.returns.clear()
        self.timestamps.clear()
        self.current_ewma_vol = None
        self.current_garch_vol = None
        self.ewma_variance = None
        self.update_count = 0
        self.last_refit_time = None
        self.garch_model = None
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'window_size': self.window_size,
            'current_data_points': len(self.prices),
            'update_count': self.update_count,
            'ewma_lambda': self.ewma_lambda,
            'garch_available': self.garch_available,
            'garch_fitted': self.garch_model is not None,
            'last_refit_time': self.last_refit_time,
            'min_periods': self.min_periods
        }


if __name__ == "__main__":
    # 测试波动率跟踪器

    from qtrade.simulation.data_loader.data_utils import ATMOptionsIterator
    
    # 1. 初始化
    data_folder = '/home/ubuntu/options_trading/data/okx_data_processor/options_geeks/fixed_options_with_iv_greeks'
    iterator = ATMOptionsIterator(data_folder, silent_mode=True)
    vol_tracker = VolTracker(window_size=96, ewma_lambda=0.94)
    
    print(f"📊 数据范围: {iterator.dates[0]} 到 {iterator.dates[-1]}")
    
    # 2. 选择测试范围 (最近3天)
    test_start = iterator.dates[-10]
    test_end = iterator.dates[-1]
    
    print(f"🔄 测试范围: {test_start} 到 {test_end}")


    # 3. Pipeline处理
    count = 0
    for data_point in iterator.iterate_date_range(test_start, test_end):
        # 更新波动率
        vol_result = vol_tracker.add_price(
            data_point['spot_price'], 
            data_point['time']
        )
        
        count += 1
        
        # 每100个点显示一次
        if count % 100 == 0 and vol_result['ewma_vol_annualized']:
            print(f"时间点{count}: {data_point['time'].strftime('%m-%d %H:%M')}, "
                    f"价格=${data_point['spot_price']:,.0f}, "
                    f"波动率={vol_result['ewma_vol_annualized']:.1%}")
    
    # 4. 最终结果
    final_forecast = vol_tracker.get_current_forecast()
    if final_forecast['status'] == 'ready':
        # 🆕 优先使用GARCH预测，备用EWMA
        # 🔧 暂时禁用GARCH，使用EWMA
        garch_vol = None  # vol_result.get('garch_vol_annualized')
        ewma_vol = vol_result.get('ewma_vol_annualized')
        
        # 选择可用的波动率预测
        if garch_vol is not None:
            predicted_vol = garch_vol
            vol_model = "GARCH"
        elif ewma_vol is not None:
            predicted_vol = ewma_vol
            vol_model = "EWMA"
        else:
            predicted_vol = None
            vol_model = "无"

        print(f"\n✅ 最终{vol_model}年化波动率: {predicted_vol:.1%}")
        print(f"📊 处理了 {count} 个时间点")