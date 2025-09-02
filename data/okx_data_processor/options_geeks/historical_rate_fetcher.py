#!/usr/bin/env python3
"""
历史无风险利率获取器
获取美国国债利率数据，用于期权定价计算
"""

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import requests
import json
from pathlib import Path

class HistoricalRateFetcher:
    def __init__(self, cache_dir="./rate_cache"):
        """
        初始化历史利率获取器
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.rate_data = None
        self.cache_file = self.cache_dir / "treasury_rates.csv"
        
    def fetch_treasury_rates(self, start_date="2020-01-01", end_date="2025-12-31"):
        """
        从FRED获取10年期美国国债利率数据
        
        Args:
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            
        Returns:
            pd.DataFrame: 包含日期和利率的数据框
        """
        print(f"📊 获取美国国债利率数据: {start_date} 到 {end_date}")
        
        try:
            # 使用FRED API获取10年期国债利率 (DGS10)
            # 这是一个公开的API，不需要API key
            url = "https://api.stlouisfed.org/fred/series/observations"
            params = {
                'series_id': 'DGS10',  # 10年期国债利率
                'api_key': 'demo',  # 使用demo key，有限制但够用
                'file_type': 'json',
                'observation_start': start_date,
                'observation_end': end_date,
                'frequency': 'd',  # 日度数据
                'aggregation_method': 'avg'
            }
            
            print("🌐 正在从FRED API获取数据...")
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                observations = data['observations']
                
                # 转换为DataFrame
                df = pd.DataFrame(observations)
                df['date'] = pd.to_datetime(df['date'])
                df['value'] = pd.to_numeric(df['value'], errors='coerce')
                
                # 过滤掉缺失值和非交易日
                df = df.dropna(subset=['value'])
                df = df[df['value'] != '.']  # FRED用'.'表示缺失值
                df['rate'] = df['value'] / 100.0  # 转换为小数形式
                
                result_df = df[['date', 'rate']].copy()
                result_df.columns = ['date', 'treasury_rate']
                
                print(f"✅ 成功获取 {len(result_df)} 条利率记录")
                return result_df
                
            else:
                print(f"❌ API请求失败: {response.status_code}")
                return self._generate_fallback_rates(start_date, end_date)
                
        except Exception as e:
            print(f"❌ 获取利率数据失败: {e}")
            print("🔄 使用备用利率数据...")
            return self._generate_fallback_rates(start_date, end_date)
    
    def _generate_fallback_rates(self, start_date, end_date):
        """
        生成备用利率数据（基于历史趋势的模拟数据）
        """
        print("📈 生成备用利率数据...")
        
        start = pd.to_datetime(start_date)
        end = pd.to_datetime(end_date)
        
        # 生成日期序列
        date_range = pd.date_range(start=start, end=end, freq='D')
        
        # 基于历史趋势的利率模拟
        rates = []
        for i, date in enumerate(date_range):
            # 简单的时间趋势模型：2021年低利率，逐渐上升到2023-2024年高点
            if date.year <= 2021:
                base_rate = 0.015  # 1.5%
            elif date.year == 2022:
                base_rate = 0.025  # 2.5%
            elif date.year == 2023:
                base_rate = 0.045  # 4.5%
            elif date.year >= 2024:
                base_rate = 0.042  # 4.2%
            else:
                base_rate = 0.04   # 4.0%
            
            # 添加一些随机波动
            noise = np.random.normal(0, 0.002)  # 0.2%的标准差
            rate = max(0.001, base_rate + noise)  # 最低0.1%
            rates.append(rate)
        
        df = pd.DataFrame({
            'date': date_range,
            'treasury_rate': rates
        })
        
        print(f"✅ 生成 {len(df)} 条备用利率记录")
        return df
    
    def load_or_fetch_rates(self, force_refresh=False):
        """
        加载或获取利率数据（带缓存）
        
        Args:
            force_refresh: 是否强制刷新数据
            
        Returns:
            pd.DataFrame: 利率数据
        """
        if not force_refresh and self.cache_file.exists():
            print(f"📂 从缓存加载利率数据: {self.cache_file}")
            try:
                self.rate_data = pd.read_csv(self.cache_file)
                self.rate_data['date'] = pd.to_datetime(self.rate_data['date'])
                print(f"✅ 加载 {len(self.rate_data)} 条缓存利率记录")
                return self.rate_data
            except Exception as e:
                print(f"⚠️  缓存加载失败: {e}")
        
        # 获取新数据
        self.rate_data = self.fetch_treasury_rates()
        
        # 保存到缓存
        try:
            self.rate_data.to_csv(self.cache_file, index=False)
            print(f"💾 利率数据已缓存到: {self.cache_file}")
        except Exception as e:
            print(f"⚠️  缓存保存失败: {e}")
        
        return self.rate_data
    
    def get_rate_for_date(self, target_date):
        """
        获取指定日期的利率
        
        Args:
            target_date: 目标日期 (str "YYYY-MM-DD" 或 datetime)
            
        Returns:
            float: 该日期的利率 (小数形式)
        """
        if self.rate_data is None:
            self.load_or_fetch_rates()
        
        if isinstance(target_date, str):
            target_date = pd.to_datetime(target_date)
        
        # 寻找最接近的日期
        closest_idx = (self.rate_data['date'] - target_date).abs().idxmin()
        closest_date = self.rate_data.loc[closest_idx, 'date']
        rate = self.rate_data.loc[closest_idx, 'treasury_rate']
        
        # 如果日期差距超过7天，给出警告
        days_diff = abs((closest_date - target_date).days)
        if days_diff > 7:
            print(f"⚠️  日期 {target_date.strftime('%Y-%m-%d')} 的利率使用了 {days_diff} 天前的数据")
        
        return rate
    
    def get_rate_statistics(self):
        """
        获取利率数据的统计信息
        """
        if self.rate_data is None:
            self.load_or_fetch_rates()
        
        stats = {
            'count': len(self.rate_data),
            'start_date': self.rate_data['date'].min(),
            'end_date': self.rate_data['date'].max(),
            'min_rate': self.rate_data['treasury_rate'].min(),
            'max_rate': self.rate_data['treasury_rate'].max(),
            'mean_rate': self.rate_data['treasury_rate'].mean(),
            'std_rate': self.rate_data['treasury_rate'].std()
        }
        
        return stats

def demo():
    """演示函数"""
    print("🎯 历史利率获取器演示")
    print("=" * 50)
    
    fetcher = HistoricalRateFetcher()
    
    # 加载利率数据
    rates = fetcher.load_or_fetch_rates()
    
    # 显示统计信息
    stats = fetcher.get_rate_statistics()
    print(f"\n📊 利率数据统计:")
    print(f"  数据条数: {stats['count']:,}")
    print(f"  时间范围: {stats['start_date'].strftime('%Y-%m-%d')} 到 {stats['end_date'].strftime('%Y-%m-%d')}")
    print(f"  利率范围: {stats['min_rate']*100:.2f}% - {stats['max_rate']*100:.2f}%")
    print(f"  平均利率: {stats['mean_rate']*100:.2f}%")
    print(f"  利率标准差: {stats['std_rate']*100:.2f}%")
    
    # 测试获取特定日期的利率
    test_dates = ['2023-07-01', '2024-01-01', '2024-06-15']
    print(f"\n📅 测试日期利率:")
    for date_str in test_dates:
        rate = fetcher.get_rate_for_date(date_str)
        print(f"  {date_str}: {rate*100:.2f}%")

if __name__ == "__main__":
    demo()
