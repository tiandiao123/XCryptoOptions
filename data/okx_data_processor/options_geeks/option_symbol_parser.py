#!/usr/bin/env python3
"""
期权符号解析器
解析OKX期权符号格式：BTC-USD-YYMMDD-STRIKE-C/P
"""

import re
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

class OptionSymbolParser:
    def __init__(self):
        """初始化期权符号解析器"""
        # OKX期权符号格式：BTC-USD-YYMMDD-STRIKE-C/P
        self.pattern = r'^([A-Z]+)-([A-Z]+)-(\d{6})-(\d+)-([CP])$'
        self.compiled_pattern = re.compile(self.pattern)
    
    def parse_symbol(self, symbol: str) -> Dict:
        """
        解析期权符号
        
        Args:
            symbol: 期权符号，如 "BTC-USD-240101-38000-C"
            
        Returns:
            Dict: 包含解析结果的字典
        """
        match = self.compiled_pattern.match(symbol.strip())
        
        if not match:
            raise ValueError(f"无效的期权符号格式: {symbol}")
        
        base_asset, quote_asset, date_str, strike_str, option_type = match.groups()
        
        # 解析日期 (YYMMDD -> YYYY-MM-DD)
        try:
            # 处理两位年份：20-29 -> 2020-2029, 00-19 -> 2000-2019
            year_2digit = int(date_str[:2])
            if year_2digit >= 20:
                year = 2000 + year_2digit
            else:
                year = 2000 + year_2digit  # 可以根据需要调整到2100+
                
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            
            # 创建到期日期时间（OKX期权通常在UTC 08:00到期）
            expiry_date = datetime(year, month, day, 8, 0, 0, tzinfo=timezone.utc)
            
        except ValueError as e:
            raise ValueError(f"无效的到期日期格式: {date_str} in {symbol}") from e
        
        # 解析执行价格
        try:
            strike_price = float(strike_str)
        except ValueError as e:
            raise ValueError(f"无效的执行价格格式: {strike_str} in {symbol}") from e
        
        # 期权类型
        is_call = (option_type == 'C')
        option_type_full = 'Call' if is_call else 'Put'
        
        return {
            'symbol': symbol,
            'base_asset': base_asset,
            'quote_asset': quote_asset,
            'expiry_date': expiry_date,
            'expiry_date_str': expiry_date.strftime('%Y-%m-%d'),
            'strike_price': strike_price,
            'option_type': option_type,
            'option_type_full': option_type_full,
            'is_call': is_call,
            'raw_date': date_str,
            'currency_pair': f"{base_asset}-{quote_asset}"
        }
    
    def calculate_time_to_expiry(self, current_time: str, expiry_date: datetime) -> float:
        """
        计算到期时间（年化）
        
        Args:
            current_time: 当前时间字符串 "YYYY-MM-DD HH:MM:SS UTC"
            expiry_date: 到期日期 (datetime with timezone)
            
        Returns:
            float: 到期时间（年）
        """
        try:
            # 解析当前时间
            current_dt = datetime.strptime(current_time, "%Y-%m-%d %H:%M:%S UTC")
            current_dt = current_dt.replace(tzinfo=timezone.utc)
            
            # 计算时间差
            time_diff = expiry_date - current_dt
            days = time_diff.total_seconds() / 86400.0
            
            # 转换为年，最小值为1e-6（避免除零）
            T = max(days / 365.0, 1e-6)
            
            return T
            
        except Exception as e:
            raise ValueError(f"时间计算错误: current_time={current_time}, expiry_date={expiry_date}") from e
    
    def parse_and_calculate_time(self, symbol: str, current_time: str) -> Dict:
        """
        解析符号并计算到期时间
        
        Args:
            symbol: 期权符号
            current_time: 当前时间字符串
            
        Returns:
            Dict: 包含解析结果和时间计算的字典
        """
        parsed = self.parse_symbol(symbol)
        time_to_expiry = self.calculate_time_to_expiry(current_time, parsed['expiry_date'])
        
        parsed['time_to_expiry'] = time_to_expiry
        parsed['current_time'] = current_time
        
        # 添加一些有用的标志
        parsed['is_expired'] = time_to_expiry <= 1e-6
        parsed['days_to_expiry'] = time_to_expiry * 365.0
        
        return parsed
    
    def batch_parse(self, symbols: list, current_times: list = None) -> list:
        """
        批量解析期权符号
        
        Args:
            symbols: 期权符号列表
            current_times: 当前时间列表（可选，与symbols长度一致）
            
        Returns:
            list: 解析结果列表
        """
        results = []
        
        for i, symbol in enumerate(symbols):
            try:
                if current_times and i < len(current_times):
                    result = self.parse_and_calculate_time(symbol, current_times[i])
                else:
                    result = self.parse_symbol(symbol)
                
                results.append(result)
                
            except Exception as e:
                # 记录错误但继续处理
                error_result = {
                    'symbol': symbol,
                    'error': str(e),
                    'parsed_successfully': False
                }
                results.append(error_result)
        
        return results
    
    def validate_symbol(self, symbol: str) -> bool:
        """
        验证期权符号格式是否正确
        
        Args:
            symbol: 期权符号
            
        Returns:
            bool: 是否有效
        """
        try:
            self.parse_symbol(symbol)
            return True
        except:
            return False

def demo():
    """演示函数"""
    print("🎯 期权符号解析器演示")
    print("=" * 50)
    
    parser = OptionSymbolParser()
    
    # 测试符号
    test_symbols = [
        "BTC-USD-240101-38000-C",
        "BTC-USD-250915-120000-P", 
        "BTC-USD-231215-45000-C",
        "ETH-USD-240630-3000-P"
    ]
    
    test_time = "2024-01-01 12:00:00 UTC"
    
    print("📊 解析测试:")
    for symbol in test_symbols:
        try:
            result = parser.parse_and_calculate_time(symbol, test_time)
            print(f"\n期权符号: {symbol}")
            print(f"  基础资产: {result['base_asset']}")
            print(f"  到期日: {result['expiry_date_str']}")
            print(f"  执行价格: ${result['strike_price']:,}")
            print(f"  期权类型: {result['option_type_full']}")
            print(f"  到期时间: {result['time_to_expiry']:.4f} 年 ({result['days_to_expiry']:.1f} 天)")
            print(f"  是否到期: {result['is_expired']}")
            
        except Exception as e:
            print(f"\n❌ 解析失败 {symbol}: {e}")
    
    # 测试批量解析
    print(f"\n🚀 批量解析测试:")
    times = [test_time] * len(test_symbols)
    batch_results = parser.batch_parse(test_symbols, times)
    
    successful = sum(1 for r in batch_results if r.get('parsed_successfully', True))
    print(f"  成功解析: {successful}/{len(test_symbols)}")
    
    # 测试符号验证
    print(f"\n✅ 符号验证测试:")
    valid_symbols = ["BTC-USD-240101-38000-C", "INVALID-SYMBOL"]
    for symbol in valid_symbols:
        is_valid = parser.validate_symbol(symbol)
        print(f"  {symbol}: {'✅ 有效' if is_valid else '❌ 无效'}")

if __name__ == "__main__":
    demo()
