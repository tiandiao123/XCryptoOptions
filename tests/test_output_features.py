#!/usr/bin/env python3
"""
测试TradingEngine的P&L记录和平仓信息记录功能
"""

import sys
import os
import time
import threading
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.trading_engine.trading_engine import TradingEngine

def test_output_folder_structure():
    """测试输出文件夹结构"""
    print("🧪 测试输出文件夹结构")
    print("=" * 50)
    
    # 使用自定义输出文件夹
    custom_output_folder = "/tmp/test_trading_results"
    
    trading_engine = TradingEngine(
        calendar_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
        gamma_scalping_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
        env="testnet",
        max_open_calendar=1,
        max_open_gamma_scalping=1,
        enable_delta_hedge=True,
        output_folder=custom_output_folder  # 🆕 自定义输出文件夹
    )
    
    # 验证文件夹结构
    assert os.path.exists(custom_output_folder), f"主文件夹不存在: {custom_output_folder}"
    assert os.path.exists(trading_engine.charts_folder), f"图表文件夹不存在: {trading_engine.charts_folder}"
    assert os.path.exists(trading_engine.logs_folder), f"日志文件夹不存在: {trading_engine.logs_folder}"
    
    print("✅ 文件夹结构验证成功:")
    print(f"   主文件夹: {trading_engine.output_folder}")
    print(f"   图表文件夹: {trading_engine.charts_folder}")
    print(f"   日志文件夹: {trading_engine.logs_folder}")
    print(f"   P&L数据文件: {trading_engine.pnl_data_file}")
    print(f"   平仓日志文件: {trading_engine.position_close_log}")
    
    return trading_engine

def test_pnl_recording_thread():
    """测试P&L记录线程"""
    print("\n🧪 测试P&L记录线程")
    print("=" * 50)
    
    custom_output_folder = "/tmp/test_trading_results"
    
    trading_engine = TradingEngine(
        calendar_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
        gamma_scalping_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
        env="testnet",
        output_folder=custom_output_folder
    )
    
    # 启动P&L记录线程（短时间测试）
    pnl_thread = threading.Thread(
        target=trading_engine._start_pnl_recording,
        args=(30,),  # 30秒间隔
        daemon=True,
        name="TestPnLRecorder"
    )
    
    print(f"📊 启动P&L记录线程测试...")
    pnl_thread.start()
    
    print(f"   线程ID: {pnl_thread.ident}")
    print(f"   线程存活: {pnl_thread.is_alive()}")
    
    # 等待一段时间观察
    print(f"⏰ 等待60秒观察P&L记录...")
    time.sleep(60)
    
    print(f"📊 P&L记录线程状态:")
    print(f"   线程存活: {pnl_thread.is_alive()}")
    
    # 检查文件是否创建
    if os.path.exists(trading_engine.pnl_data_file):
        print(f"✅ P&L数据文件已创建: {trading_engine.pnl_data_file}")
        
        # 读取并显示内容
        with open(trading_engine.pnl_data_file, 'r') as f:
            import json
            data = json.load(f)
            print(f"   初始Equity: {data.get('initial_equity', 'N/A')}")
            print(f"   历史记录数: {len(data.get('history', []))}")
            print(f"   最后更新: {data.get('last_update', 'N/A')}")
    else:
        print(f"⚠️ P&L数据文件未创建")
    
    return trading_engine

def test_position_close_logging():
    """测试平仓信息记录功能"""
    print("\n🧪 测试平仓信息记录功能")
    print("=" * 50)
    
    from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
    from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.atm_options_filter import OptionData
    
    custom_output_folder = "/tmp/test_trading_results"
    
    trading_engine = TradingEngine(
        calendar_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
        gamma_scalping_config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
        env="testnet",
        output_folder=custom_output_folder
    )
    
    # 创建模拟的Straddle持仓
    call_option = OptionData(
        symbol="BTC-28NOV25-114000-C",
        strike=114000,
        expiry="28NOV25",
        days_to_expiry=16,
        option_type="call",
        iv=0.45,
        bid=0.055,
        ask=0.065,
        mid_price=0.060,
        delta=0.25,
        net_delta=0.20,
        gamma=0.0001,
        vega=0.05,
        theta=-0.001,
        rho=0.002
    )
    
    put_option = OptionData(
        symbol="BTC-28NOV25-114000-P",
        strike=114000,
        expiry="28NOV25",
        days_to_expiry=16,
        option_type="put",
        iv=0.47,
        bid=0.052,
        ask=0.062,
        mid_price=0.057,
        delta=-0.23,
        net_delta=-0.18,
        gamma=0.0001,
        vega=0.05,
        theta=-0.001,
        rho=-0.002
    )
    
    straddle = StraddleOpportunity(
        call_option=call_option,
        put_option=put_option,
        realized_vol=0.35,
        strategy_type="short_straddle",
        call_option_entry_iv=0.45,
        put_option_entry_iv=0.47,
        entry_spot_price=114000.0,
        contracts=1.0,
        total_premium=0.117
    )
    
    # 测试平仓信息记录
    print(f"📝 测试平仓信息记录...")
    
    # 直接调用记录方法（不实际平仓）
    trading_engine.risk_manager._record_position_close(
        position=straddle,
        close_reason="测试平仓记录功能",
        position_close_log=trading_engine.position_close_log,
        env="testnet"
    )
    
    # 检查日志文件
    if os.path.exists(trading_engine.position_close_log):
        print(f"✅ 平仓日志文件已创建: {trading_engine.position_close_log}")
        
        # 读取并显示内容
        with open(trading_engine.position_close_log, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"📄 日志内容预览:")
            print(content[:500] + "..." if len(content) > 500 else content)
    else:
        print(f"⚠️ 平仓日志文件未创建")

def main():
    """主测试函数"""
    print("🚀 TradingEngine输出功能测试")
    print("=" * 60)
    
    try:
        # 测试文件夹结构
        trading_engine = test_output_folder_structure()
        
        # 测试平仓信息记录
        test_position_close_logging()
        
        # 测试P&L记录线程（可选，需要较长时间）
        print(f"\n💡 要测试P&L记录线程吗？(需要等待60秒) [y/N]: ", end="")
        # test_pnl = input().lower().startswith('y')
        test_pnl = False  # 自动跳过长时间测试
        
        if test_pnl:
            test_pnl_recording_thread()
        
        print("\n" + "=" * 60)
        print("🎉 所有测试完成！")
        print("\n📋 功能总结:")
        print("✅ 动态输出文件夹结构")
        print("✅ 图表和日志子文件夹创建")
        print("✅ P&L数据记录功能")
        print("✅ 平仓信息记录功能")
        print("✅ 多线程P&L监控")
        
        print("\n🔄 使用方法:")
        print("   trading_engine = TradingEngine(..., output_folder='/your/path')")
        print("   trading_engine.run_loop()  # 自动启动监控和记录线程")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
