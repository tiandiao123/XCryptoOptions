# -*- coding: utf-8 -*-
"""
Gamma Scalping - 真实数据EWMA波动率跟踪器
基于Binance API获取真实历史K线数据
专门为Selling Straddle策略提供准确的realized volatility计算
"""

import numpy as np
import requests
import time
import pandas as pd
import os
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Optional, Dict, Any, List
import yaml
from pathlib import Path


class RealDataEWMAVolTracker:
    """
    基于真实历史数据的EWMA波动率跟踪器 - 支持多时间级别
    
    功能:
    1. 支持多种时间间隔: 1m, 5m, 15m, 30m, 1h, 4h, 1d
    2. 启动时从Binance获取历史K线数据
    3. 使用真实价格数据计算EWMA波动率
    4. 每次predict调用时检查并更新最新数据
    5. 维护指定数量数据点的滚动窗口
    """
    
    # 支持的时间间隔映射
    SUPPORTED_INTERVALS = {
        '1m': {'binance': '1m', 'minutes': 1, 'name': '1分钟'},
        '5m': {'binance': '5m', 'minutes': 5, 'name': '5分钟'},
        '15m': {'binance': '15m', 'minutes': 15, 'name': '15分钟'},
        '30m': {'binance': '30m', 'minutes': 30, 'name': '30分钟'},
        '1h': {'binance': '1h', 'minutes': 60, 'name': '1小时'},
        '4h': {'binance': '4h', 'minutes': 240, 'name': '4小时'},
        '1d': {'binance': '1d', 'minutes': 1440, 'name': '1天'}
    }
    
    def __init__(self, 
                 symbol: str = "BTCUSDT",
                 interval: str = "30m",  # 支持的时间间隔
                 window_size: int = 96,  # 数据点数量
                 ewma_lambda: float = 0.94,
                 min_periods: int = 20):
        """
        初始化真实数据EWMA波动率跟踪器
        
        Args:
            symbol: 交易对符号 (BTCUSDT, ETHUSDT等)
            interval: 时间间隔 ('1m', '5m', '15m', '30m', '1h', '4h', '1d')
            window_size: 滚动窗口大小 (数据点数)
            ewma_lambda: EWMA衰减因子 (0-1, 越大越平滑)
            min_periods: 最小计算周期
        """
        # 验证时间间隔
        if interval not in self.SUPPORTED_INTERVALS:
            raise ValueError(f"不支持的时间间隔: {interval}. 支持的间隔: {list(self.SUPPORTED_INTERVALS.keys())}")
        
        self.symbol = symbol
        self.interval = interval
        self.interval_info = self.SUPPORTED_INTERVALS[interval]
        self.window_size = window_size
        self.ewma_lambda = ewma_lambda
        self.min_periods = min_periods
        
        # 计算年化因子 (基于时间间隔)
        minutes_per_period = self.interval_info['minutes']
        periods_per_year = 365 * 24 * 60 / minutes_per_period
        self.annualization_factor = periods_per_year
        
        # 数据存储 - 存储K线数据
        self.timestamps = deque(maxlen=window_size)
        self.close_prices = deque(maxlen=window_size)
        self.returns = deque(maxlen=window_size-1)
        
        # EWMA状态
        self.ewma_variance = None
        self.current_ewma_vol = None
        
        # 状态跟踪
        self.last_update_time = None
        self.is_initialized = False
        
        # CSV缓存设置 - 使用当前文件所在目录下的cache文件夹
        current_file_dir = Path(__file__).parent
        self.cache_dir = current_file_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.csv_file = self.cache_dir / f"{symbol}_{interval}_klines.csv"
        
        print(f"🚀 初始化真实数据EWMA波动率跟踪器")
        print(f"   交易对: {symbol}")
        print(f"   时间间隔: {self.interval_info['name']} ({interval})")
        print(f"   窗口大小: {window_size} 个数据点")
        print(f"   年化因子: {self.annualization_factor:.0f} (每年周期数)")
        print(f"   EWMA λ: {ewma_lambda}")
        print(f"   CSV缓存: {self.csv_file}")
        
        # 启动时获取历史数据
        self._initialize_with_historical_data()
    
    def _calculate_lookback_days(self) -> int:
        """
        根据时间间隔和窗口大小计算需要回看的天数
        
        Returns:
            需要的历史数据天数
        """
        minutes_per_period = self.interval_info['minutes']
        total_minutes = self.window_size * minutes_per_period
        days_needed = total_minutes / (24 * 60)
        
        # 至少获取2天数据，最多30天
        return max(2, min(30, int(days_needed * 1.2)))  # 多获取20%以确保数据充足
    
    def _initialize_with_historical_data(self):
        """
        从Binance获取历史K线数据进行初始化
        """
        print(f"\n📊 从Binance获取{self.symbol}历史K线数据...")
        
        try:
            # 计算时间范围 - 确保获取到当前时间的连续数据
            current_time = int(time.time() * 1000)  # 当前时间戳(毫秒)
            
            # 计算需要多少个周期来填满window_size
            period_ms = self.interval_info['minutes'] * 60 * 1000
            required_time_span = self.window_size * period_ms
            
            # 从当前时间往回推算开始时间
            start_time = current_time - required_time_span
            
            print(f"📅 获取连续到当前时间的{self.interval_info['name']}K线数据...")
            print(f"   时间范围: {datetime.fromtimestamp(start_time/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} 到 {datetime.fromtimestamp(current_time/1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} (UTC)")
            
            # 调用Binance API获取K线数据
            klines = self._fetch_binance_klines(start_time, current_time)
            
            if not klines:
                raise Exception("未能获取到K线数据")
            
            print(f"✅ 获取到 {len(klines)} 个{self.interval_info['name']}K线数据")
            
            # 保存K线数据到CSV (初始化)
            self._save_klines_to_csv(klines, "initial")
            
            # 处理K线数据 - 取最新的window_size个数据，确保连续到当前时间
            latest_klines = klines[-self.window_size:] if len(klines) >= self.window_size else klines
            
            print(f"📊 处理最新的{len(latest_klines)}个K线数据点")
            
            for kline in latest_klines:
                timestamp = kline[0]  # 开盘时间
                close_price = float(kline[4])  # 收盘价
                
                self.timestamps.append(timestamp)
                self.close_prices.append(close_price)
            
            # 验证数据连续性
            if len(self.timestamps) > 1:
                time_gaps = []
                for i in range(1, len(self.timestamps)):
                    gap_minutes = (self.timestamps[i] - self.timestamps[i-1]) / (1000 * 60)
                    time_gaps.append(gap_minutes)
                
                expected_interval = self.interval_info['minutes']
                unusual_gaps = [gap for gap in time_gaps if abs(gap - expected_interval) > 0.1]
                
                if unusual_gaps:
                    print(f"⚠️ 发现{len(unusual_gaps)}个异常时间间隔: {unusual_gaps[:3]}")
                else:
                    print(f"✅ 数据时间间隔正常 (期望{expected_interval}分钟)")
            
            # 计算收益率
            self._calculate_returns()
            
            # 初始化EWMA
            self._initialize_ewma()
            
            self.is_initialized = True
            self.last_update_time = datetime.now()
            
            print(f"✅ 历史数据初始化完成")
            print(f"   数据点数: {len(self.close_prices)}")
            print(f"   价格范围: ${min(self.close_prices):,.2f} - ${max(self.close_prices):,.2f}")
            print(f"   时间跨度: {self._get_time_span()}")
            
            if self.current_ewma_vol:
                annualized_vol = self.current_ewma_vol * np.sqrt(self.annualization_factor)
                print(f"   初始EWMA波动率: {annualized_vol:.1%}")
            
        except Exception as e:
            print(f"❌ 历史数据初始化失败: {e}")
            self.is_initialized = False
    
    def _get_time_span(self) -> str:
        """获取数据时间跨度描述"""
        if not self.timestamps:
            return "无数据"
        
        # 使用UTC时区转换时间戳
        start_time = datetime.fromtimestamp(self.timestamps[0] / 1000, tz=timezone.utc)
        end_time = datetime.fromtimestamp(self.timestamps[-1] / 1000, tz=timezone.utc)
        
        return f"{start_time.strftime('%m-%d %H:%M')} 到 {end_time.strftime('%m-%d %H:%M')} (UTC)"
    
    def _klines_to_dataframe(self, klines: List) -> pd.DataFrame:
        """
        将Binance K线数据转换为DataFrame
        
        Args:
            klines: Binance API返回的K线数据
            
        Returns:
            包含人类可读时间格式的DataFrame
        """
        if not klines:
            return pd.DataFrame()
        
        # Binance K线数据格式: [timestamp, open, high, low, close, volume, ...]
        df_data = []
        for kline in klines:
            timestamp_ms = kline[0]
            # 使用UTC时区进行转换，避免本地时区影响
            timestamp_dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            
            row = {
                'timestamp_ms': timestamp_ms,
                'datetime': timestamp_dt.strftime('%Y-%m-%d %H:%M:%S'),
                'date': timestamp_dt.strftime('%Y-%m-%d'),
                'time': timestamp_dt.strftime('%H:%M:%S'),
                'open': float(kline[1]),
                'high': float(kline[2]),
                'low': float(kline[3]),
                'close': float(kline[4]),
                'volume': float(kline[5]),
                'interval': self.interval,
                'symbol': self.symbol,
                'timezone': 'UTC'  # 明确标注时区
            }
            df_data.append(row)
        
        df = pd.DataFrame(df_data)
        return df
    
    def _save_klines_to_csv(self, klines: List, operation: str = "initial"):
        """
        保存K线数据到CSV文件
        
        Args:
            klines: K线数据
            operation: 操作类型 ("initial", "update")
        """
        try:
            if not klines:
                print("⚠️ 没有K线数据需要保存")
                return
            
            # 转换为DataFrame
            new_df = self._klines_to_dataframe(klines)
            
            if new_df.empty:
                print("⚠️ K线数据转换失败")
                return
            
            if operation == "initial" or not self.csv_file.exists():
                # 初始化时保存所有数据，但只保留window_size数量
                df_to_save = new_df.tail(self.window_size)
                df_to_save.to_csv(self.csv_file, index=False)
                print(f"💾 初始CSV保存: {len(df_to_save)}条记录 -> {self.csv_file}")
                
            else:
                # 更新时追加新数据，然后保持window_size大小
                # 先读取现有数据
                existing_df = pd.read_csv(self.csv_file)
                
                # 合并数据并去重
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df = combined_df.drop_duplicates(subset=['timestamp_ms'], keep='last')
                combined_df = combined_df.sort_values('timestamp_ms')
                
                # 只保留最新的window_size条记录
                final_df = combined_df.tail(self.window_size)
                final_df.to_csv(self.csv_file, index=False)
                
                print(f"💾 CSV更新: 添加{len(new_df)}条新记录，保持{len(final_df)}条记录 -> {self.csv_file}")
                
                # 显示最新几条记录用于验证
                print("📊 最新3条记录:")
                for _, row in final_df.tail(3).iterrows():
                    print(f"   {row['datetime']} | ${row['close']:,.2f}")
                    
        except Exception as e:
            print(f"❌ CSV保存失败: {e}")
    
    def _load_csv_data(self) -> Optional[pd.DataFrame]:
        """
        从CSV文件加载现有数据
        
        Returns:
            DataFrame或None
        """
        try:
            if not self.csv_file.exists():
                return None
            
            df = pd.read_csv(self.csv_file)
            if df.empty:
                return None
                
            print(f"📂 从CSV加载了{len(df)}条历史记录")
            return df
            
        except Exception as e:
            print(f"⚠️ CSV加载失败: {e}")
            return None
    
    def _fetch_binance_klines(self, start_time: int, end_time: int) -> List:
        """
        从Binance API获取K线数据 - 支持分批获取超过1000条的数据
        
        Args:
            start_time: 开始时间戳(毫秒)
            end_time: 结束时间戳(毫秒)
            
        Returns:
            K线数据列表
        """
        url = "https://api.binance.com/api/v3/klines"
        all_klines = []
        
        # 计算需要的数据点数
        period_ms = self.interval_info['minutes'] * 60 * 1000
        expected_points = int((end_time - start_time) / period_ms) + 1
        
        print(f"📊 预期获取{expected_points}个数据点")
        
        current_start = start_time
        batch_count = 0
        
        while current_start < end_time:
            batch_count += 1
            
            # 计算这一批的结束时间 (每批最多1000个数据点)
            batch_end = min(current_start + (1000 * period_ms), end_time)
            
            params = {
                'symbol': self.symbol,
                'interval': self.interval_info['binance'],
                'startTime': current_start,
                'endTime': batch_end,
                'limit': 1000
            }
            
            try:
                print(f"   批次{batch_count}: {datetime.fromtimestamp(current_start/1000, tz=timezone.utc).strftime('%m-%d %H:%M')} 到 {datetime.fromtimestamp(batch_end/1000, tz=timezone.utc).strftime('%m-%d %H:%M')}")
                
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                
                batch_klines = response.json()
                
                if not isinstance(batch_klines, list):
                    raise Exception(f"API返回格式错误: {batch_klines}")
                
                if batch_klines:
                    # 检查是否与前一批有重叠，避免重复数据
                    if batch_count > 1 and all_klines and batch_klines:
                        # 检查第一个数据点是否与上一批的最后一个重复
                        last_existing_timestamp = all_klines[-1][0]
                        first_new_timestamp = batch_klines[0][0]
                        
                        if first_new_timestamp <= last_existing_timestamp:
                            # 找到第一个不重复的数据点
                            skip_count = 0
                            for kline in batch_klines:
                                if kline[0] <= last_existing_timestamp:
                                    skip_count += 1
                                else:
                                    break
                            batch_klines = batch_klines[skip_count:]
                            if skip_count > 0:
                                print(f"      跳过{skip_count}个重复数据点")
                    
                    if batch_klines:  # 确保还有数据
                        all_klines.extend(batch_klines)
                        print(f"      添加{len(batch_klines)}条数据")
                        
                        # 更新下一批的开始时间 - 从最后一个数据点的下一分钟开始
                        last_timestamp = batch_klines[-1][0]
                        current_start = last_timestamp + period_ms
                    else:
                        print(f"      所有数据都重复，跳过此批次")
                        break
                else:
                    print(f"      无数据返回")
                    break
                    
                # 添加小延迟避免API限制
                time.sleep(0.1)
                
            except Exception as e:
                print(f"❌ 批次{batch_count}请求失败: {e}")
                if batch_count == 1:  # 如果第一批就失败，返回空
                    return []
                else:  # 如果不是第一批，返回已获取的数据
                    break
        
        print(f"✅ 总共获取到{len(all_klines)}条K线数据 (分{batch_count}批)")
        return all_klines
    
    def _calculate_returns(self):
        """计算对数收益率"""
        self.returns.clear()
        
        if len(self.close_prices) < 2:
            return
        
        prices = list(self.close_prices)
        for i in range(1, len(prices)):
            ret = np.log(prices[i] / prices[i-1])
            self.returns.append(ret)
    
    def _initialize_ewma(self):
        """初始化EWMA方差"""
        if len(self.returns) < self.min_periods:
            return
        
        # 使用历史收益率的样本方差作为初始EWMA方差
        returns_array = np.array(self.returns)
        self.ewma_variance = np.var(returns_array, ddof=1)
        self.current_ewma_vol = np.sqrt(self.ewma_variance)
        
        print(f"📈 EWMA初始化: 方差={self.ewma_variance:.6f}, 波动率={self.current_ewma_vol:.4f}")
    
    def _update_latest_data(self) -> bool:
        """
        检查并更新最新的K线数据
        
        Returns:
            是否有新数据更新
        """
        try:
            # 计算查询时间范围 (获取最近几个周期的数据)
            current_time = int(time.time() * 1000)
            lookback_periods = 3  # 获取最近3个周期
            period_ms = self.interval_info['minutes'] * 60 * 1000
            start_time = current_time - lookback_periods * period_ms
            
            latest_klines = self._fetch_binance_klines(start_time, current_time)
            
            if not latest_klines:
                return False
            
            # 检查是否有新数据
            latest_kline = latest_klines[-1]  # 最新的K线
            latest_timestamp = latest_kline[0]
            
            # 如果时间戳比我们最新的数据新，则添加
            if not self.timestamps or latest_timestamp > self.timestamps[-1]:
                close_price = float(latest_kline[4])
                
                # 保存新数据到CSV (更新模式)
                self._save_klines_to_csv([latest_kline], "update")
                
                # 添加新数据点
                self.timestamps.append(latest_timestamp)
                self.close_prices.append(close_price)
                
                # 计算新的收益率
                if len(self.close_prices) >= 2:
                    new_return = np.log(self.close_prices[-1] / self.close_prices[-2])
                    self.returns.append(new_return)
                    
                    # 更新EWMA
                    self._update_ewma(new_return)
                
                # 使用UTC时区显示时间
                time_str = datetime.fromtimestamp(latest_timestamp/1000, tz=timezone.utc).strftime('%m-%d %H:%M (UTC)')
                print(f"📊 更新数据: 价格=${close_price:,.2f}, 时间={time_str}")
                return True
            
            return False
            
        except Exception as e:
            print(f"⚠️ 更新最新数据失败: {e}")
            return False
    
    def _update_ewma(self, new_return: float):
        """
        使用新收益率更新EWMA方差
        
        Args:
            new_return: 新的对数收益率
        """
        if self.ewma_variance is None:
            # 如果还没有初始化，使用当前所有数据初始化
            self._initialize_ewma()
        else:
            # 递推更新EWMA方差
            self.ewma_variance = (
                self.ewma_lambda * self.ewma_variance + 
                (1 - self.ewma_lambda) * new_return**2
            )
            self.current_ewma_vol = np.sqrt(self.ewma_variance)
    
    def predict(self) -> Dict[str, Any]:
        """
        预测当前的realized volatility
        
        每次调用时会:
        1. 检查并更新最新数据
        2. 重新计算EWMA波动率
        3. 返回年化波动率
        
        Returns:
            包含波动率预测结果的字典
        """
        if not self.is_initialized:
            return {
                'success': False,
                'error': '跟踪器未初始化',
                'realized_vol_annualized': None
            }
        
        # 1. 更新最新数据
        has_new_data = self._update_latest_data()
        
        # 2. 检查数据充足性
        if len(self.returns) < self.min_periods:
            return {
                'success': False,
                'error': f'数据不足 ({len(self.returns)}/{self.min_periods})',
                'realized_vol_annualized': None
            }
        
        # 3. 计算年化波动率
        if self.current_ewma_vol is None:
            return {
                'success': False,
                'error': 'EWMA未初始化',
                'realized_vol_annualized': None
            }
        
        # 年化波动率 (基于时间间隔自动计算)
        annualized_vol = self.current_ewma_vol * np.sqrt(self.annualization_factor)
        
        # 计算日波动率 (假设一天有多少个周期)
        periods_per_day = 24 * 60 / self.interval_info['minutes']
        daily_vol = self.current_ewma_vol * np.sqrt(periods_per_day)
        
        self.last_update_time = datetime.now()
        
        return {
            'success': True,
            'realized_vol_annualized': annualized_vol,
            'realized_vol_daily': daily_vol,
            'realized_vol_period': self.current_ewma_vol,  # 单周期波动率
            'data_points': len(self.close_prices),
            'returns_count': len(self.returns),
            'latest_price': self.close_prices[-1] if self.close_prices else None,
            'last_update': self.last_update_time,
            'has_new_data': has_new_data,
            'symbol': self.symbol,
            'interval': self.interval,
            'interval_name': self.interval_info['name'],
            'annualization_factor': self.annualization_factor
        }
    
    def get_status(self) -> Dict[str, Any]:
        """获取跟踪器状态"""
        return {
            'is_initialized': self.is_initialized,
            'symbol': self.symbol,
            'interval': self.interval,
            'interval_name': self.interval_info['name'],
            'window_size': self.window_size,
            'data_points': len(self.close_prices),
            'returns_count': len(self.returns),
            'ewma_lambda': self.ewma_lambda,
            'last_update': self.last_update_time,
            'latest_price': self.close_prices[-1] if self.close_prices else None,
            'price_range': {
                'min': min(self.close_prices) if self.close_prices else None,
                'max': max(self.close_prices) if self.close_prices else None
            },
            'annualization_factor': self.annualization_factor
        }
    
    def verify_csv_data(self) -> Dict[str, Any]:
        """
        验证CSV数据的准确性和完整性
        
        Returns:
            验证结果字典
        """
        try:
            if not self.csv_file.exists():
                return {
                    'success': False,
                    'error': 'CSV文件不存在',
                    'file_path': str(self.csv_file)
                }
            
            df = pd.read_csv(self.csv_file)
            
            if df.empty:
                return {
                    'success': False,
                    'error': 'CSV文件为空',
                    'file_path': str(self.csv_file)
                }
            
            # 验证数据
            verification = {
                'success': True,
                'file_path': str(self.csv_file),
                'total_records': len(df),
                'expected_records': self.window_size,
                'time_range': {
                    'start': df.iloc[0]['datetime'] if len(df) > 0 else None,
                    'end': df.iloc[-1]['datetime'] if len(df) > 0 else None
                },
                'price_range': {
                    'min': df['close'].min(),
                    'max': df['close'].max(),
                    'latest': df.iloc[-1]['close'] if len(df) > 0 else None
                },
                'data_consistency': {
                    'has_duplicates': df['timestamp_ms'].duplicated().any(),
                    'is_sorted': df['timestamp_ms'].is_monotonic_increasing,
                    'missing_values': df.isnull().sum().to_dict()
                }
            }
            
            # 检查时间间隔是否正确
            if len(df) > 1:
                df['timestamp_dt'] = pd.to_datetime(df['timestamp_ms'], unit='ms')
                time_diffs = df['timestamp_dt'].diff().dt.total_seconds() / 60  # 分钟
                expected_interval_minutes = self.interval_info['minutes']
                
                # 允许一些容差
                correct_intervals = (time_diffs.dropna() == expected_interval_minutes).sum()
                total_intervals = len(time_diffs.dropna())
                
                verification['time_intervals'] = {
                    'expected_minutes': expected_interval_minutes,
                    'correct_count': int(correct_intervals),
                    'total_count': int(total_intervals),
                    'accuracy_pct': (correct_intervals / total_intervals * 100) if total_intervals > 0 else 0
                }
            
            return verification
            
        except Exception as e:
            return {
                'success': False,
                'error': f'验证失败: {e}',
                'file_path': str(self.csv_file)
            }
    
    def print_csv_summary(self):
        """打印CSV数据摘要"""
        verification = self.verify_csv_data()
        
        print(f"\n📋 CSV数据验证报告:")
        print(f"   文件路径: {verification['file_path']}")
        
        if not verification['success']:
            print(f"   ❌ 验证失败: {verification['error']}")
            return
        
        print(f"   ✅ 验证成功")
        print(f"   📊 记录数量: {verification['total_records']}/{verification['expected_records']}")
        print(f"   ⏰ 时间范围: {verification['time_range']['start']} 到 {verification['time_range']['end']}")
        print(f"   💰 价格范围: ${verification['price_range']['min']:,.2f} - ${verification['price_range']['max']:,.2f}")
        print(f"   📈 最新价格: ${verification['price_range']['latest']:,.2f}")
        
        # 数据一致性
        consistency = verification['data_consistency']
        print(f"   🔍 数据质量:")
        print(f"      重复数据: {'有' if consistency['has_duplicates'] else '无'}")
        print(f"      时间排序: {'正确' if consistency['is_sorted'] else '错误'}")
        
        # 时间间隔准确性
        if 'time_intervals' in verification:
            intervals = verification['time_intervals']
            print(f"   ⏱️ 时间间隔:")
            print(f"      期望间隔: {intervals['expected_minutes']}分钟")
            print(f"      准确率: {intervals['accuracy_pct']:.1f}% ({intervals['correct_count']}/{intervals['total_count']})")
    
    def get_csv_tail(self, n: int = 5) -> pd.DataFrame:
        """
        获取CSV文件的最后n条记录
        
        Args:
            n: 记录数量
            
        Returns:
            DataFrame
        """
        try:
            if not self.csv_file.exists():
                return pd.DataFrame()
            
            df = pd.read_csv(self.csv_file)
            return df.tail(n)
            
        except Exception as e:
            print(f"❌ 读取CSV失败: {e}")
            return pd.DataFrame()


def create_vol_tracker_from_config(config: Dict[str, Any]) -> RealDataEWMAVolTracker:
    """从配置创建波动率跟踪器"""
    vol_config = config.get("vol_tracker_config", {})
    
    return RealDataEWMAVolTracker(
        symbol=vol_config.get("symbol", "BTCUSDT"),
        window_size=vol_config.get("window_size", 96),
        ewma_lambda=vol_config.get("ewma_lambda", 0.94),
        min_periods=vol_config.get("min_periods", 20)
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
    # 测试真实数据EWMA波动率跟踪器 - 支持多时间级别
    print("🚀 测试真实数据EWMA波动率跟踪器（多时间级别）...")
    
    # 测试不同时间级别
    test_intervals = ['5m', '30m', '1h']
    
    for interval in test_intervals:
        print(f"\n{'='*60}")
        print(f"🔍 测试 {interval} 时间级别")
        print('='*60)
        
        try:
            # 根据时间级别调整窗口大小
            if interval == '5m':
                window_size = 288  # 288个5分钟 = 24小时
            elif interval == '30m':
                window_size = 96   # 96个30分钟 = 48小时
            elif interval == '1h':
                window_size = 72   # 72个1小时 = 3天
            else:
                window_size = 96
            
            # 创建跟踪器 (会自动初始化历史数据)
            vol_tracker = RealDataEWMAVolTracker(
                symbol="BTCUSDT", 
                interval=interval,
                window_size=window_size
            )
            
            if vol_tracker.is_initialized:
                print(f"\n✅ {interval} 跟踪器初始化成功")
                
                # 显示状态
                status = vol_tracker.get_status()
                print(f"📊 状态信息:")
                print(f"   时间级别: {status['interval']} ({status.get('interval_name', '')})")
                print(f"   数据点: {status['data_points']}")
                print(f"   最新价格: ${status['latest_price']:,.2f}")
                print(f"   年化因子: {status.get('annualization_factor', 0):.0f}")
                
                # 显示CSV验证报告
                vol_tracker.print_csv_summary()
                
                # 测试predict函数
                print(f"\n🔮 测试predict函数:")
                result = vol_tracker.predict()
                
                if result['success']:
                    print(f"✅ 预测成功:")
                    print(f"   年化波动率: {result['realized_vol_annualized']:.1%}")
                    print(f"   日波动率: {result['realized_vol_daily']:.1%}")
                    print(f"   周期波动率: {result['realized_vol_period']:.4f}")
                    print(f"   最新价格: ${result['latest_price']:,.2f}")
                    print(f"   有新数据: {result['has_new_data']}")
                    
                    # 验证波动率合理性
                    vol = result['realized_vol_annualized']
                    if 0.10 <= vol <= 2.0:  # 10%-200%
                        print(f"   ✅ 波动率在合理范围内")
                    else:
                        print(f"   ⚠️ 波动率可能异常")
                        
                    # 显示CSV最新记录
                    print(f"\n📄 CSV最新5条记录:")
                    csv_tail = vol_tracker.get_csv_tail(5)
                    if not csv_tail.empty:
                        for _, row in csv_tail.iterrows():
                            print(f"   {row['datetime']} | ${row['close']:,.2f} | {row['interval']}")
                    
                else:
                    print(f"❌ 预测失败: {result['error']}")
                
            else:
                print(f"❌ {interval} 跟踪器初始化失败")
                
        except Exception as e:
            print(f"❌ {interval} 测试失败: {e}")
        
        # 测试间隔
        if interval != test_intervals[-1]:
            print(f"\n⏳ 等待2秒后测试下一个时间级别...")
            time.sleep(2)
    
    print(f"\n{'='*60}")
    print("📋 多时间级别支持总结:")
    print("✅ 支持的时间间隔:")
    for key, value in RealDataEWMAVolTracker.SUPPORTED_INTERVALS.items():
        print(f"   {key}: {value['name']} (每周期{value['minutes']}分钟)")
    
    print(f"\n💡 使用建议:")
    print(f"   - 高频交易: 使用 1m 或 5m")
    print(f"   - 中频交易: 使用 15m 或 30m")
    print(f"   - 低频交易: 使用 1h 或 4h")
    print(f"   - 长期分析: 使用 1d")
    
    print("\n✅ 测试完成!")
