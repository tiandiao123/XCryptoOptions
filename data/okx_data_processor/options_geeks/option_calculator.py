#!/usr/bin/env python3
"""
期权计算器 - 核心计算引擎
集成历史利率、符号解析和IV/希腊字母计算
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Any
import warnings

# 导入我们的组件
from historical_rate_fetcher import HistoricalRateFetcher
from option_symbol_parser import OptionSymbolParser

# 导入BS计算函数
from compute_bs_iv import (
    implied_vol_from_coin_price,
    bs_delta,
    calculate_pa_delta, 
    bs_gamma,
    pa_gamma,
    bs_vega,
    pa_vega
)

class OptionCalculator:
    def __init__(self, rate_cache_dir="./rate_cache"):
        """
        初始化期权计算器
        
        Args:
            rate_cache_dir: 利率数据缓存目录
        """
        print("🚀 初始化期权计算器...")
        
        # 初始化组件
        self.rate_fetcher = HistoricalRateFetcher(cache_dir=rate_cache_dir)
        self.symbol_parser = OptionSymbolParser()
        
        # 加载历史利率数据
        print("📊 加载历史利率数据...")
        self.rate_fetcher.load_or_fetch_rates()
        
        # 显示利率统计
        stats = self.rate_fetcher.get_rate_statistics()
        print(f"✅ 利率数据加载完成:")
        print(f"   时间范围: {stats['start_date'].strftime('%Y-%m-%d')} 到 {stats['end_date'].strftime('%Y-%m-%d')}")
        print(f"   利率范围: {stats['min_rate']*100:.2f}% - {stats['max_rate']*100:.2f}%")
        print(f"   平均利率: {stats['mean_rate']*100:.2f}%")
        
        print("✅ 期权计算器初始化完成")
    
    def calculate_option_metrics(self, row_data: Dict) -> Dict:
        """
        为单行期权数据计算所有指标
        
        Args:
            row_data: 包含期权数据的字典，必须包含:
                - symbol: 期权符号
                - time: 时间字符串
                - open: 期权开盘价 (币本位)
                - spot_open: 现货开盘价
                
        Returns:
            Dict: 计算结果，包含IV、希腊字母、利率等
        """
        try:
            # 1. 解析期权符号和计算到期时间
            parsed = self.symbol_parser.parse_and_calculate_time(
                row_data['symbol'], 
                row_data['time']
            )
            
            # 2. 检查是否已到期
            if parsed['is_expired']:
                return self._create_expired_result(row_data, parsed)
            
            # 3. 获取历史利率
            historical_rate = self.rate_fetcher.get_rate_for_date(row_data['time'].split(' ')[0])
            
            # 4. 准备计算参数
            S = float(row_data['spot_open'])  # 现货价格
            K = parsed['strike_price']        # 执行价格
            T = parsed['time_to_expiry']      # 到期时间
            r = historical_rate               # 无风险利率
            q = 0.0                          # 分红率（OKX假设为0）
            option_price_coin = float(row_data['open'])  # 期权价格（币本位）
            is_call = parsed['is_call']       # 期权类型
            
            # 5. 验证输入数据
            validation_result = self._validate_inputs(S, K, T, r, option_price_coin)
            if validation_result:
                return validation_result
            
            # 6. 计算隐含波动率
            try:
                iv = implied_vol_from_coin_price(
                    price_coin=option_price_coin,
                    opt_type='c' if is_call else 'p',
                    S=S, K=K, T=T, r=r, q=q,
                    model="bs"
                )
            except Exception as e:
                return self._create_error_result(row_data, parsed, historical_rate, f"IV计算失败: {str(e)}")
            
            # 7. 计算希腊字母
            try:
                # Delta
                bs_delta_value = bs_delta(S, K, T, r, q, iv, is_call=is_call)
                pa_delta_value = calculate_pa_delta(S, K, T, r, iv, option_price_coin, is_call=is_call)
                
                # Gamma
                bs_gamma_value = bs_gamma(S, K, T, r, q, iv)
                pa_gamma_value = pa_gamma(S, K, T, r, q, iv, option_price_coin, is_call=is_call)
                
                # Vega
                bs_vega_value = bs_vega(S, K, T, r, q, iv)
                pa_vega_value = pa_vega(S, K, T, r, q, iv, option_price_coin, is_call=is_call)
                
            except Exception as e:
                return self._create_error_result(row_data, parsed, historical_rate, f"希腊字母计算失败: {str(e)}")
            
            # 8. 组装结果
            result = {
                # 原始数据
                'symbol': row_data['symbol'],
                'time': row_data['time'],
                'spot_price': S,
                'strike_price': K,
                'option_price_coin': option_price_coin,
                'option_type': parsed['option_type'],
                'is_call': is_call,
                
                # 时间相关
                'time_to_expiry': T,
                'days_to_expiry': T * 365.0,
                'expiry_date': parsed['expiry_date_str'],
                
                # 利率
                'historical_rate': historical_rate,
                
                # 隐含波动率
                'iv': iv,
                'iv_percent': iv * 100.0,
                
                # Delta
                'bs_delta': bs_delta_value,
                'pa_delta': pa_delta_value,
                
                # Gamma
                'bs_gamma': bs_gamma_value,
                'pa_gamma': pa_gamma_value,
                
                # Vega
                'bs_vega': bs_vega_value,
                'pa_vega': pa_vega_value,
                
                # 状态
                'calculation_success': True,
                'error': None
            }
            
            return result
            
        except Exception as e:
            return self._create_error_result(row_data, {}, 0.0, f"计算器错误: {str(e)}")
    
    def _validate_inputs(self, S, K, T, r, option_price_coin):
        """验证输入参数"""
        if S <= 0:
            return self._create_error_result({}, {}, r, f"无效的现货价格: {S}")
        
        if K <= 0:
            return self._create_error_result({}, {}, r, f"无效的执行价格: {K}")
        
        if T <= 1e-6:
            return self._create_error_result({}, {}, r, f"无效的到期时间: {T}")
        
        if option_price_coin <= 0:
            return self._create_error_result({}, {}, r, f"无效的期权价格: {option_price_coin}")
        
        if r < 0 or r > 1:
            return self._create_error_result({}, {}, r, f"无效的利率: {r}")
        
        return None  # 验证通过
    
    def _create_expired_result(self, row_data, parsed):
        """创建已到期期权的结果"""
        return {
            'symbol': row_data.get('symbol', ''),
            'time': row_data.get('time', ''),
            'spot_price': float(row_data.get('spot_open', 0)),
            'strike_price': parsed.get('strike_price', 0),
            'option_price_coin': float(row_data.get('open', 0)),
            'option_type': parsed.get('option_type', ''),
            'is_call': parsed.get('is_call', True),
            'time_to_expiry': 0.0,
            'days_to_expiry': 0.0,
            'expiry_date': parsed.get('expiry_date_str', ''),
            'historical_rate': np.nan,
            'iv': np.nan,
            'iv_percent': np.nan,
            'bs_delta': np.nan,
            'pa_delta': np.nan,
            'bs_gamma': np.nan,
            'pa_gamma': np.nan,
            'bs_vega': np.nan,
            'pa_vega': np.nan,
            'calculation_success': False,
            'error': 'expired'
        }
    
    def _create_error_result(self, row_data, parsed, historical_rate, error_msg):
        """创建错误结果"""
        return {
            'symbol': row_data.get('symbol', ''),
            'time': row_data.get('time', ''),
            'spot_price': float(row_data.get('spot_open', 0)) if 'spot_open' in row_data else np.nan,
            'strike_price': parsed.get('strike_price', np.nan),
            'option_price_coin': float(row_data.get('open', 0)) if 'open' in row_data else np.nan,
            'option_type': parsed.get('option_type', ''),
            'is_call': parsed.get('is_call', True),
            'time_to_expiry': parsed.get('time_to_expiry', np.nan),
            'days_to_expiry': parsed.get('time_to_expiry', 0) * 365.0,
            'expiry_date': parsed.get('expiry_date_str', ''),
            'historical_rate': historical_rate,
            'iv': np.nan,
            'iv_percent': np.nan,
            'bs_delta': np.nan,
            'pa_delta': np.nan,
            'bs_gamma': np.nan,
            'pa_gamma': np.nan,
            'bs_vega': np.nan,
            'pa_vega': np.nan,
            'calculation_success': False,
            'error': error_msg
        }
    
    def process_dataframe_row(self, row) -> Dict:
        """
        处理DataFrame的单行数据
        
        Args:
            row: pandas Series对象
            
        Returns:
            Dict: 计算结果
        """
        row_data = {
            'symbol': row['symbol'],
            'time': row['time'],
            'open': row['open'],
            'spot_open': row['spot_open']
        }
        
        return self.calculate_option_metrics(row_data)
    
    def get_summary_stats(self, results: list) -> Dict:
        """
        获取批量计算结果的统计信息
        
        Args:
            results: 计算结果列表
            
        Returns:
            Dict: 统计信息
        """
        if not results:
            return {}
        
        successful_results = [r for r in results if r.get('calculation_success', False)]
        total_count = len(results)
        success_count = len(successful_results)
        
        if success_count == 0:
            return {
                'total_count': total_count,
                'success_count': 0,
                'success_rate': 0.0,
                'error_rate': 100.0
            }
        
        # 提取数值数据
        ivs = [r['iv'] for r in successful_results if not np.isnan(r['iv'])]
        rates = [r['historical_rate'] for r in successful_results if not np.isnan(r['historical_rate'])]
        deltas = [r['bs_delta'] for r in successful_results if not np.isnan(r['bs_delta'])]
        
        stats = {
            'total_count': total_count,
            'success_count': success_count,
            'success_rate': (success_count / total_count) * 100.0,
            'error_rate': ((total_count - success_count) / total_count) * 100.0,
        }
        
        if ivs:
            stats.update({
                'iv_mean': np.mean(ivs),
                'iv_std': np.std(ivs),
                'iv_min': np.min(ivs),
                'iv_max': np.max(ivs)
            })
        
        if rates:
            stats.update({
                'rate_mean': np.mean(rates),
                'rate_std': np.std(rates),
                'rate_min': np.min(rates),
                'rate_max': np.max(rates)
            })
        
        if deltas:
            stats.update({
                'delta_mean': np.mean(deltas),
                'delta_std': np.std(deltas)
            })
        
        return stats

def demo():
    """演示函数"""
    print("🎯 期权计算器演示")
    print("=" * 50)
    
    # 创建计算器
    calculator = OptionCalculator()
    
    # 测试数据
    test_data = {
        'symbol': 'BTC-USD-240101-38000-C',
        'time': '2024-01-01 12:00:00 UTC',
        'open': 0.06,  # 期权价格（币本位）
        'spot_open': 42500.0  # 现货价格
    }
    
    print(f"\n📊 计算期权指标:")
    print(f"期权符号: {test_data['symbol']}")
    print(f"时间: {test_data['time']}")
    print(f"期权价格: {test_data['open']} BTC")
    print(f"现货价格: ${test_data['spot_open']:,}")
    
    # 计算指标
    result = calculator.calculate_option_metrics(test_data)
    
    if result['calculation_success']:
        print(f"\n✅ 计算成功:")
        print(f"  隐含波动率: {result['iv']:.4f} ({result['iv_percent']:.2f}%)")
        print(f"  历史利率: {result['historical_rate']*100:.2f}%")
        print(f"  到期时间: {result['time_to_expiry']:.4f} 年 ({result['days_to_expiry']:.1f} 天)")
        print(f"  BS Delta: {result['bs_delta']:.4f}")
        print(f"  PA Delta: {result['pa_delta']:.4f}")
        print(f"  BS Gamma: {result['bs_gamma']:.6f}")
        print(f"  PA Gamma: {result['pa_gamma']:.6f}")
        print(f"  BS Vega: {result['bs_vega']:.4f}")
        print(f"  PA Vega: {result['pa_vega']:.6f}")
    else:
        print(f"\n❌ 计算失败: {result['error']}")

if __name__ == "__main__":
    demo()
