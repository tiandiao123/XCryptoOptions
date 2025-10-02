"""
Gamma Scalping - EWMA波动率跟踪器
专门为Selling Straddle策略提供realized volatility计算
简化版本：只使用EWMA方法，不包含GARCH模型
支持历史数据初始化和持久化缓存
"""

import numpy as np
import pickle
import json
from datetime import datetime, timedelta
from collections import deque
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
import yaml
import time

# 导入Deribit API获取现货价格
from qtrade.demo_trade.deribit_order_placer.options_orderbook import get_index_price


class EWMAVolTracker:
    """
    简化的EWMA波动率跟踪器 - 专用于Gamma Scalping
    
    功能:
    1. EWMA (指数加权移动平均) 波动率预测
    2. 滚动窗口价格数据管理
    3. 实时更新机制
    4. 历史数据初始化和持久化缓存
    5. 专门为selling straddle策略优化
    """
    
    def __init__(self, 
                 window_size: int = 96,  # 2天的30分钟数据 (48*2)
                 ewma_lambda: float = 0.94,  # EWMA衰减因子
                 min_periods: int = 20,  # 最小计算周期
                 annualization_factor: float = 17520,  # 年化因子 (365*24*2 for 30min)
                 cache_file: str = None):  # 缓存文件路径
        """
        初始化EWMA波动率跟踪器
        
        Args:
            window_size: 滚动窗口大小 (数据点数)
            ewma_lambda: EWMA衰减因子 (0-1, 越大越平滑)
            min_periods: 开始计算的最小数据点数
            annualization_factor: 年化因子
            cache_file: 缓存文件路径，用于持久化存储
        """
        self.window_size = window_size
        self.ewma_lambda = ewma_lambda
        self.min_periods = min_periods
        self.annualization_factor = annualization_factor
        
        # 缓存文件设置
        if cache_file is None:
            cache_dir = Path("/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/gamma_scalping/cache")
            cache_dir.mkdir(exist_ok=True)
            self.cache_file = cache_dir / "ewma_vol_cache.pkl"
        else:
            self.cache_file = Path(cache_file)
        
        # 数据存储
        self.prices = deque(maxlen=window_size)
        self.returns = deque(maxlen=window_size-1)
        self.timestamps = deque(maxlen=window_size)
        
        # 波动率预测
        self.current_ewma_vol = None
        self.ewma_variance = None
        
        # 统计信息
        self.update_count = 0
        self.last_update_time = None
        self.last_api_update = None
        self.currency = "BTC"
        self.env = "testnet"
        
        print(f"✅ EWMA波动率跟踪器初始化完成")
        print(f"   窗口大小: {window_size}, EWMA λ: {ewma_lambda}")
        print(f"   缓存文件: {self.cache_file}")
    
    def initialize_with_historical_data(self, currency: str = "BTC", env: str = "testnet", 
                                      interval_minutes: int = 30) -> bool:
        """
        使用历史数据初始化跟踪器
        
        由于Deribit没有直接的历史K线API，这里实现几种策略：
        1. 尝试从缓存文件加载历史数据
        2. 如果缓存不存在或过期，使用模拟数据初始化
        3. 后续通过实时API调用补充数据
        
        Args:
            currency: 币种
            env: 环境
            interval_minutes: 数据间隔（分钟）
            
        Returns:
            是否成功初始化
        """
        self.currency = currency
        self.env = env
        
        print(f"🔍 初始化{currency}历史数据 (间隔: {interval_minutes}分钟)...")
        
        # 1. 尝试从缓存加载
        if self._load_from_cache():
            print(f"✅ 从缓存加载了{len(self.prices)}个历史数据点")
            return True
        
        # 2. 缓存不可用，尝试构建初始数据
        print("⚠️ 缓存不可用，开始构建初始数据...")
        
        try:
            # 获取当前价格作为基准
            current_price = get_index_price(currency, env)
            current_time = datetime.now()
            
            print(f"💰 当前{currency}价格: ${current_price:,.2f}")
            
            # 生成模拟历史数据（基于随机游走）
            historical_data = self._generate_bootstrap_data(
                current_price, current_time, interval_minutes
            )
            
            # 添加历史数据点
            for price, timestamp in historical_data:
                self.add_price(price, timestamp, save_cache=False)  # 批量添加时不保存缓存
            
            # 保存缓存
            self._save_to_cache()
            
            print(f"✅ 初始化完成，生成了{len(self.prices)}个历史数据点")
            return True
            
        except Exception as e:
            print(f"❌ 历史数据初始化失败: {e}")
            return False
    
    def _generate_bootstrap_data(self, current_price: float, current_time: datetime, 
                               interval_minutes: int) -> List[Tuple[float, datetime]]:
        """
        生成引导数据（模拟历史价格）
        
        使用几何布朗运动模拟历史价格路径
        
        Args:
            current_price: 当前价格
            current_time: 当前时间
            interval_minutes: 时间间隔
            
        Returns:
            (价格, 时间戳)列表
        """
        
        historical_data = []
        
        # 参数设置
        num_points = self.window_size
        dt = interval_minutes / (60 * 24 * 365)  # 转换为年化时间增量
        vol_estimate = 0.8  # 假设年化波动率80%（加密货币典型水平）
        drift = 0.0  # 假设无漂移
        
        # 从当前时间往回生成
        price = current_price
        for i in range(num_points):
            # 时间往回推
            timestamp = current_time - timedelta(minutes=interval_minutes * (num_points - 1 - i))
            
            # 几何布朗运动
            if i > 0:
                dW = np.random.normal(0, np.sqrt(dt))
                price_change = price * (drift * dt + vol_estimate * dW)
                price = max(price + price_change, current_price * 0.5)  # 防止价格过低
            
            historical_data.append((price, timestamp))
        
        return historical_data
    
    def add_price(self, price: float, timestamp: datetime, save_cache: bool = True) -> Dict[str, Any]:
        """
        添加新的价格数据点并更新波动率预测
        
        Args:
            price: 现货价格
            timestamp: 时间戳
            save_cache: 是否保存缓存
            
        Returns:
            dict: 更新结果，包含预测的波动率
        """
        self.prices.append(price)
        self.timestamps.append(timestamp)
        self.update_count += 1
        self.last_update_time = timestamp
        
        # 计算对数收益率
        if len(self.prices) >= 2:
            ret = np.log(price / self.prices[-2])
            self.returns.append(ret)
        
        # 更新波动率预测
        result = self._update_ewma_volatility()
        
        # 保存缓存（可选）
        if save_cache and self.update_count % 10 == 0:  # 每10次更新保存一次
            self._save_to_cache()
        
        return result
    
    def _update_ewma_volatility(self) -> Dict[str, Any]:
        """更新EWMA波动率预测"""
        result = {
            'timestamp': self.timestamps[-1] if self.timestamps else None,
            'price': self.prices[-1] if self.prices else None,
            'ewma_vol_period': None,
            'ewma_vol_daily': None,
            'ewma_vol_annualized': None,
            'data_points': len(self.prices),
            'returns_count': len(self.returns),
            'is_ready': False
        }
        
        # 检查是否有足够的数据
        if len(self.returns) < self.min_periods:
            result['status'] = f'需要更多数据 ({len(self.returns)}/{self.min_periods})'
            return result
        
        # 计算EWMA波动率
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
        
        # 计算不同时间尺度的波动率
        self.current_ewma_vol = np.sqrt(self.ewma_variance)
        
        result.update({
            'ewma_vol_period': self.current_ewma_vol,
            'ewma_vol_daily': self.current_ewma_vol * np.sqrt(48),  # 48个30分钟周期
            'ewma_vol_annualized': self.current_ewma_vol * np.sqrt(self.annualization_factor),
            'is_ready': True,
            'status': 'ready'
        })
        
        return result
    
    def _save_to_cache(self) -> bool:
        """保存数据到缓存文件"""
        try:
            cache_data = {
                'prices': list(self.prices),
                'returns': list(self.returns),
                'timestamps': [ts.isoformat() for ts in self.timestamps],
                'ewma_variance': self.ewma_variance,
                'current_ewma_vol': self.current_ewma_vol,
                'update_count': self.update_count,
                'last_update_time': self.last_update_time.isoformat() if self.last_update_time else None,
                'currency': self.currency,
                'env': self.env,
                'config': {
                    'window_size': self.window_size,
                    'ewma_lambda': self.ewma_lambda,
                    'min_periods': self.min_periods,
                    'annualization_factor': self.annualization_factor
                },
                'cache_time': datetime.now().isoformat()
            }
            
            with open(self.cache_file, 'wb') as f:
                pickle.dump(cache_data, f)
            
            return True
            
        except Exception as e:
            print(f"⚠️ 保存缓存失败: {e}")
            return False
    
    def _load_from_cache(self) -> bool:
        """从缓存文件加载数据"""
        try:
            if not self.cache_file.exists():
                return False
            
            with open(self.cache_file, 'rb') as f:
                cache_data = pickle.load(f)
            
            # 检查缓存是否过期（超过1小时）
            cache_time = datetime.fromisoformat(cache_data['cache_time'])
            if datetime.now() - cache_time > timedelta(hours=1):
                print("⚠️ 缓存已过期（超过1小时）")
                return False
            
            # 检查配置是否匹配
            config = cache_data.get('config', {})
            if (config.get('window_size') != self.window_size or 
                config.get('ewma_lambda') != self.ewma_lambda):
                print("⚠️ 缓存配置不匹配")
                return False
            
            # 恢复数据
            self.prices.extend(cache_data['prices'])
            self.returns.extend(cache_data['returns'])
            self.timestamps.extend([
                datetime.fromisoformat(ts) for ts in cache_data['timestamps']
            ])
            
            self.ewma_variance = cache_data.get('ewma_variance')
            self.current_ewma_vol = cache_data.get('current_ewma_vol')
            self.update_count = cache_data.get('update_count', 0)
            
            if cache_data.get('last_update_time'):
                self.last_update_time = datetime.fromisoformat(cache_data['last_update_time'])
            
            self.currency = cache_data.get('currency', 'BTC')
            self.env = cache_data.get('env', 'testnet')
            
            return True
            
        except Exception as e:
            print(f"⚠️ 加载缓存失败: {e}")
            return False
    
    def get_current_realized_vol(self) -> Optional[float]:
        """
        获取当前的年化realized volatility
        
        Returns:
            年化realized volatility，如果数据不足则返回None
        """
        if len(self.returns) < self.min_periods or self.current_ewma_vol is None:
            return None
        
        return self.current_ewma_vol * np.sqrt(self.annualization_factor)
    
    def get_historical_volatility(self, periods: int = 48) -> Optional[float]:
        """
        计算简单历史波动率 (标准差方法)
        
        Args:
            periods: 计算周期数
            
        Returns:
            年化历史波动率
        """
        if len(self.returns) < periods:
            return None
        
        recent_returns = list(self.returns)[-periods:]
        return np.std(recent_returns, ddof=1) * np.sqrt(self.annualization_factor)
    
    def update_from_api(self, currency: str = None, env: str = None) -> Dict[str, Any]:
        """
        从Deribit API获取最新现货价格并更新波动率
        
        Args:
            currency: 币种（可选，使用实例默认值）
            env: 环境（可选，使用实例默认值）
            
        Returns:
            更新结果
        """
        try:
            # 使用实例的默认值
            currency = currency or self.currency
            env = env or self.env
            
            # 获取现货价格
            spot_price = get_index_price(currency, env)
            current_time = datetime.now()
            
            # 更新波动率
            result = self.add_price(spot_price, current_time)
            
            result.update({
                'api_update': True,
                'currency': currency,
                'spot_price': spot_price
            })
            
            self.last_api_update = current_time
            
            return result
            
        except Exception as e:
            return {
                'api_update': False,
                'error': str(e),
                'timestamp': datetime.now()
            }
    
    def get_volatility_summary(self) -> Dict[str, Any]:
        """
        获取波动率跟踪器的完整状态摘要
        
        Returns:
            状态摘要字典
        """
        current_vol = self.get_current_realized_vol()
        hist_vol_1d = self.get_historical_volatility(48)  # 1天
        hist_vol_3d = self.get_historical_volatility(144)  # 3天
        
        return {
            'status': 'ready' if current_vol is not None else 'insufficient_data',
            'data_points': len(self.prices),
            'returns_count': len(self.returns),
            'min_required': self.min_periods,
            'last_update': self.last_update_time,
            'last_api_update': self.last_api_update,
            'update_count': self.update_count,
            
            # 波动率指标
            'realized_vol_ewma': current_vol,
            'realized_vol_1d': hist_vol_1d,
            'realized_vol_3d': hist_vol_3d,
            
            # 配置参数
            'window_size': self.window_size,
            'ewma_lambda': self.ewma_lambda,
            'annualization_factor': self.annualization_factor,
            
            # 最新价格信息
            'latest_price': self.prices[-1] if self.prices else None,
            'price_change_pct': self._calculate_price_change() if len(self.prices) >= 2 else None,
            
            # 缓存信息
            'cache_file': str(self.cache_file),
            'currency': self.currency,
            'env': self.env
        }
    
    def _calculate_price_change(self) -> float:
        """计算最新价格变化百分比"""
        if len(self.prices) < 2:
            return 0.0
        
        return (self.prices[-1] - self.prices[-2]) / self.prices[-2]
    
    def reset(self):
        """重置跟踪器"""
        self.prices.clear()
        self.returns.clear()
        self.timestamps.clear()
        self.current_ewma_vol = None
        self.ewma_variance = None
        self.update_count = 0
        self.last_update_time = None
        self.last_api_update = None
        
        print("🔄 EWMA波动率跟踪器已重置")
    
    def is_ready(self) -> bool:
        """检查跟踪器是否准备就绪"""
        return len(self.returns) >= self.min_periods and self.current_ewma_vol is not None
    
    def clear_cache(self) -> bool:
        """清除缓存文件"""
        try:
            if self.cache_file.exists():
                self.cache_file.unlink()
                print(f"✅ 缓存文件已清除: {self.cache_file}")
                return True
            else:
                print("⚠️ 缓存文件不存在")
                return False
        except Exception as e:
            print(f"❌ 清除缓存失败: {e}")
            return False


def create_vol_tracker_from_config(config: Dict[str, Any]) -> EWMAVolTracker:
    """
    从配置创建波动率跟踪器
    
    Args:
        config: 配置字典
        
    Returns:
        EWMAVolTracker实例
    """
    vol_config = config.get("vol_tracker_config", {})
    
    return EWMAVolTracker(
        window_size=vol_config.get("window_size", 96),
        ewma_lambda=vol_config.get("ewma_lambda", 0.94),
        min_periods=vol_config.get("min_periods", 20),
        annualization_factor=vol_config.get("annualization_factor", 17520)
    )


def load_config(config_path: str = None) -> Dict[str, Any]:
    """加载配置文件"""
    if config_path is None:
        config_path = "/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/gamma_scalping/selling_straddle.yaml"
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        print(f"❌ 配置文件加载失败: {e}")
        return {}


if __name__ == "__main__":
    # 测试EWMA波动率跟踪器 - 包含历史数据初始化和缓存功能
    print("🚀 测试EWMA波动率跟踪器（含历史数据初始化）...")
    
    # 加载配置
    config = load_config()
    
    # 创建跟踪器
    vol_tracker = create_vol_tracker_from_config(config)
    
    # 测试历史数据初始化
    print("\n📊 测试历史数据初始化...")
    success = vol_tracker.initialize_with_historical_data("BTC", "testnet", 30)
    
    if success:
        print(f"✅ 历史数据初始化成功")
        
        # 显示初始状态
        summary = vol_tracker.get_volatility_summary()
        print(f"   数据点: {summary['data_points']}")
        print(f"   状态: {summary['status']}")
        
        if summary['realized_vol_ewma']:
            print(f"   初始EWMA波动率: {summary['realized_vol_ewma']:.1%}")
        
        # 测试API更新
        print(f"\n🌐 测试API实时更新...")
        for i in range(5):
            api_result = vol_tracker.update_from_api()
            
            if api_result.get('api_update'):
                print(f"   更新#{i+1}: 价格=${api_result['spot_price']:,.2f}")
                if api_result.get('is_ready'):
                    print(f"      年化波动率: {api_result['ewma_vol_annualized']:.1%}")
            else:
                print(f"   更新#{i+1}失败: {api_result.get('error')}")
            
            # 模拟5分钟间隔
            time.sleep(1)  # 测试时用1秒代替5分钟
        
        # 最终摘要
        print(f"\n📋 最终波动率跟踪器状态:")
        final_summary = vol_tracker.get_volatility_summary()
        
        for key, value in final_summary.items():
            if key in ['realized_vol_ewma', 'realized_vol_1d', 'realized_vol_3d']:
                if value:
                    print(f"   {key}: {value:.1%}")
            elif key in ['latest_price']:
                if value:
                    print(f"   {key}: ${value:,.2f}")
            elif key in ['data_points', 'update_count', 'status']:
                print(f"   {key}: {value}")
        
        # 测试缓存功能
        print(f"\n💾 测试缓存功能...")
        print(f"   缓存文件: {vol_tracker.cache_file}")
        print(f"   缓存存在: {vol_tracker.cache_file.exists()}")
        
    else:
        print("❌ 历史数据初始化失败")
    
    print("\n✅ 测试完成!")
