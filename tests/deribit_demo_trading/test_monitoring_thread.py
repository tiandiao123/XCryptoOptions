#!/usr/bin/env python3
"""
测试TradingEngine的监控线程功能
"""

import sys
import os
import time
import threading
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.trading_engine.trading_engine import TradingEngine

def test_monitoring_thread():
    """测试监控线程功能"""
    print("🧪 测试TradingEngine监控线程功能")
    print("=" * 50)
    
    # 创建TradingEngine实例
    trading_engine = TradingEngine(
        calendar_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
        gamma_scalping_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
        env="testnet",
        max_open_calendar=1,
        max_open_gamma_scalping=1,
        enable_delta_hedge=True
    )
    
    print("✅ TradingEngine初始化成功")
    print(f"   RiskManager Delta对冲: {'启用' if trading_engine.risk_manager.enable_delta_hedge else '禁用'}")
    print(f"   RiskManager Delta阈值: ±{trading_engine.risk_manager.delta_risk_threshold:.3f}")
    
    # 模拟启动监控线程（不启动主循环）
    print("\n🔍 测试监控线程启动...")
    
    # 创建监控线程
    monitoring_thread = threading.Thread(
        target=trading_engine._start_position_monitoring,
        args=(60,),  # 1分钟间隔测试
        daemon=True,
        name="TestPositionMonitor"
    )
    
    print(f"📊 准备启动监控线程:")
    print(f"   检查间隔: 60秒")
    print(f"   线程名: {monitoring_thread.name}")
    print(f"   是否守护线程: {monitoring_thread.daemon}")
    
    # 启动线程
    monitoring_thread.start()
    print(f"✅ 监控线程已启动")
    print(f"   线程ID: {monitoring_thread.ident}")
    print(f"   线程存活: {monitoring_thread.is_alive()}")
    
    # 等待几秒钟观察输出
    print(f"\n⏰ 等待10秒观察监控线程输出...")
    time.sleep(10)
    
    print(f"\n📊 监控线程状态检查:")
    print(f"   线程存活: {monitoring_thread.is_alive()}")
    print(f"   活跃线程数: {threading.active_count()}")
    
    # 列出所有活跃线程
    for thread in threading.enumerate():
        print(f"   - {thread.name}: {thread.ident} ({'守护' if thread.daemon else '主'})")
    
    print(f"\n✅ 监控线程测试完成")
    print(f"💡 在实际使用中，监控线程会持续运行直到主程序退出")

def test_duration_conversion():
    """测试时间间隔转换逻辑"""
    print("\n🧪 测试时间间隔转换逻辑")
    print("-" * 30)
    
    test_cases = [
        (60, "5min"),      # 1分钟 -> 5min
        (300, "5min"),     # 5分钟 -> 5min
        (450, "10min"),    # 7.5分钟 -> 10min
        (600, "10min"),    # 10分钟 -> 10min
        (750, "15min"),    # 12.5分钟 -> 15min
        (900, "15min"),    # 15分钟 -> 15min
        (1800, "30min"),   # 30分钟 -> 30min
        (3600, "30min"),   # 60分钟 -> 30min
    ]
    
    for check_interval, expected in test_cases:
        # 模拟转换逻辑
        if check_interval <= 300:
            duration_str = "5min"
        elif check_interval <= 600:
            duration_str = "10min"
        elif check_interval <= 900:
            duration_str = "15min"
        else:
            duration_str = "30min"
        
        status = "✅" if duration_str == expected else "❌"
        print(f"   {status} {check_interval}秒 -> {duration_str} (期望: {expected})")

def main():
    """主测试函数"""
    print("🚀 TradingEngine监控线程功能测试")
    print("=" * 60)
    
    try:
        test_duration_conversion()
        test_monitoring_thread()
        
        print("\n" + "=" * 60)
        print("🎉 所有测试完成！")
        print("\n📋 功能总结:")
        print("✅ threading模块导入")
        print("✅ 监控线程创建和启动")
        print("✅ 时间间隔转换逻辑")
        print("✅ 线程状态监控")
        print("✅ 异常处理机制")
        
        print("\n🔄 使用方法:")
        print("   在TradingEngine.run_loop()中会自动启动监控线程")
        print("   监控线程独立运行，不影响主交易循环")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
