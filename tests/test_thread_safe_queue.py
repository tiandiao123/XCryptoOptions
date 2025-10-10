#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试ThreadSafeIndexDeque的线程安全性和功能
"""

import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor
sys.path.append('/home/ubuntu/options_trading')

from qtrade.cryptotrader.trading_engine.risk_manager import ThreadSafeIndexDeque, RiskManager

def test_thread_safety():
    """测试线程安全性"""
    
    print("🧪 测试ThreadSafeIndexDeque线程安全性")
    print("=" * 60)
    
    # 创建队列
    queue = ThreadSafeIndexDeque(max_size=20)
    
    # 测试数据
    test_data = []
    results = []
    
    def producer(thread_id, count):
        """生产者线程：添加元素"""
        thread_results = []
        for i in range(count):
            element = f"Thread-{thread_id}-Item-{i}"
            element_id = queue.add_element(element)
            thread_results.append((element_id, element))
            # 模拟一些处理时间
            time.sleep(0.001)
        results.extend(thread_results)
        print(f"✅ 生产者线程 {thread_id} 完成，添加了 {count} 个元素")
    
    def consumer(thread_id, count):
        """消费者线程：移除元素"""
        removed_count = 0
        for i in range(count):
            element = queue.pop_first_element()
            if element:
                removed_count += 1
            time.sleep(0.001)
        print(f"✅ 消费者线程 {thread_id} 完成，移除了 {removed_count} 个元素")
    
    def reader(thread_id, count):
        """读取者线程：读取元素"""
        read_count = 0
        for i in range(count):
            size = queue.size()
            if size > 0:
                # 随机读取一个元素
                index = i % size
                element = queue.get_element(index)
                if element:
                    read_count += 1
            time.sleep(0.001)
        print(f"✅ 读取者线程 {thread_id} 完成，读取了 {read_count} 次")
    
    # 启动多个线程进行并发测试
    print("🚀 启动多线程测试...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        # 提交任务
        futures = []
        
        # 3个生产者线程
        for i in range(3):
            futures.append(executor.submit(producer, f"P{i}", 10))
        
        # 2个消费者线程
        for i in range(2):
            futures.append(executor.submit(consumer, f"C{i}", 8))
        
        # 2个读取者线程
        for i in range(2):
            futures.append(executor.submit(reader, f"R{i}", 20))
        
        # 等待所有任务完成
        for future in futures:
            future.result()
    
    # 检查最终状态
    final_status = queue.get_status()
    print(f"\n📊 最终队列状态:")
    print(f"   大小: {final_status['size']}")
    print(f"   范围: [{final_status['start_id']}, {final_status['end_id']})")
    print(f"   是否为空: {final_status['is_empty']}")
    print(f"   是否已满: {final_status['is_full']}")
    
    # 显示剩余元素
    remaining_elements = queue.get_all_elements()
    if remaining_elements:
        print(f"\n📋 剩余元素 ({len(remaining_elements)}个):")
        for i, element in enumerate(remaining_elements[:5]):  # 只显示前5个
            print(f"   {i}: {element}")
        if len(remaining_elements) > 5:
            print(f"   ... 还有 {len(remaining_elements) - 5} 个元素")
    
    print("\n✅ 线程安全测试完成")

def test_basic_functionality():
    """测试基本功能"""
    
    print("\n🔧 测试基本功能")
    print("=" * 40)
    
    queue = ThreadSafeIndexDeque(max_size=5)
    
    # 测试添加元素
    print("📝 测试添加元素...")
    elements = ["A", "B", "C", "D", "E"]
    for element in elements:
        element_id = queue.add_element(element)
        print(f"   添加 '{element}' -> ID: {element_id}")
    
    print(f"   队列状态: {queue}")
    
    # 测试获取元素
    print("\n📖 测试获取元素...")
    for i in range(queue.size()):
        element = queue.get_element(i)
        print(f"   索引 {i}: {element}")
    
    # 测试弹出元素
    print("\n📤 测试弹出元素...")
    first = queue.pop_first_element()
    last = queue.pop_last_element()
    print(f"   弹出首元素: {first}")
    print(f"   弹出末元素: {last}")
    print(f"   队列状态: {queue}")
    
    # 测试查找功能
    print("\n🔍 测试查找功能...")
    found = queue.find_element(lambda x: x == "C")
    print(f"   查找 'C': {found}")
    
    # 测试过滤功能
    filtered = queue.filter_elements(lambda x: x in ["B", "D"])
    print(f"   过滤 B,D: {filtered}")
    
    print("\n✅ 基本功能测试完成")

def test_risk_manager():
    """测试风险管理器"""
    
    print("\n🛡️ 测试风险管理器")
    print("=" * 40)
    
    risk_manager = RiskManager(max_straddle_positions=3, max_calendar_positions=2)
    
    # 创建模拟数据
    from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
    from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.atm_options_filter import OptionData
    
    # 创建模拟期权数据
    call_option = OptionData(
        symbol="BTC-TEST-70000-C",
        strike=70000,
        expiry="2025-01-10",
        days_to_expiry=30,
        option_type="C",
        iv=0.8,
        bid=0.05,
        ask=0.06,
        mid_price=0.055,
        delta=0.5,
        net_delta=0.45,
        gamma=0.001,
        vega=0.1,
        theta=-0.01,
        rho=0.02
    )
    
    put_option = OptionData(
        symbol="BTC-TEST-70000-P",
        strike=70000,
        expiry="2025-01-10",
        days_to_expiry=30,
        option_type="P",
        iv=0.8,
        bid=0.05,
        ask=0.06,
        mid_price=0.055,
        delta=-0.5,
        net_delta=-0.45,
        gamma=0.001,
        vega=0.1,
        theta=-0.01,
        rho=-0.02
    )
    
    # 创建Straddle机会
    straddle = StraddleOpportunity(
        call_option=call_option,
        put_option=put_option,
        avg_iv=0.8,
        realized_vol=0.6,
        iv_premium=0.2,
        iv_premium_pct=33.33,
        strike_price=70000,
        days_to_expiry=30,
        net_delta=0.0,
        total_gamma=0.002,
        total_theta=-0.02
    )
    
    # 测试添加持仓
    print("📊 测试添加Straddle持仓...")
    for i in range(4):  # 尝试添加4个，但最大只能3个
        if risk_manager.can_add_straddle_position():
            position_id = risk_manager.add_straddle_position(straddle)
            print(f"   ✅ 添加成功，ID: {position_id}")
        else:
            print(f"   ❌ 无法添加更多持仓（已满）")
    
    # 显示状态
    risk_manager.print_status()
    
    print("\n✅ 风险管理器测试完成")

if __name__ == "__main__":
    test_basic_functionality()
    test_thread_safety()
    test_risk_manager()
