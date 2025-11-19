#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 Calendar Spread 机会日志记录功能
"""

import sys
sys.path.append('/home/ubuntu/options_trading')

from qtrade.optionstrader.master_trader.multi_shot_trading import get_calendar_spread_opportunity
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import display_calendar_opportunities

def test_opportunity_logging():
    """测试机会记录到日志文件"""
    
    print("="*70)
    print("🧪 测试 Calendar Spread 机会日志记录")
    print("="*70)
    
    # 配置文件路径
    config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    
    # 获取机会
    print("\n📊 正在获取 Calendar Spread 机会...")
    opportunity = get_calendar_spread_opportunity(
        config_path=config_path,
        currency="ETH",
        show_details=False
    )
    
    if opportunity:
        print(f"✅ 找到机会！")
        
        # 将机会列表传给显示函数（同时记录到文件）
        log_file = "/home/ubuntu/options_trading/logs/calendar_opportunities.log"
        
        print(f"\n📝 将机会详情保存到: {log_file}")
        display_calendar_opportunities([opportunity], log_file=log_file)
        
        print(f"\n✅ 测试完成！")
        print(f"   请查看日志文件: {log_file}")
        
        # 显示日志文件的最后几行
        print(f"\n📄 日志文件预览（最后30行）:")
        print("="*70)
        import subprocess
        try:
            result = subprocess.run(
                ["tail", "-n", "30", log_file],
                capture_output=True,
                text=True
            )
            print(result.stdout)
        except Exception as e:
            print(f"⚠️ 无法读取日志文件: {e}")
    else:
        print("❌ 未找到机会，无法测试日志记录")

if __name__ == "__main__":
    test_opportunity_logging()

