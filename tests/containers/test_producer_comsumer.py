#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
生产者消费者模式测试：验证 ThreadSafeMap 的线程安全性
重点展示中间过程，观察数据的生产和消费是否安全、一致
"""

import time
import threading
import random
from typing import List
from qtrade.cryptotrader.trading_engine.containers.thread_safe_map import ThreadSafeMap


class DetailedProducerConsumerTest:
    """详细的生产者消费者测试，展示中间过程"""
    
    def __init__(self):
        self.shared_map = ThreadSafeMap()
        self.produced_items: List[str] = []  # 记录生产的历史
        self.consumed_items: List[str] = []  # 记录消费的历史
        self.lock = threading.Lock()  # 用于保护日志记录
        
        # 生产和消费的计数器
        self.total_produced = 0
        self.total_consumed = 0
        
        # 控制标志
        self.running = False
        
    def log(self, thread_name: str, action: str, item: str = "", details: str = ""):
        """记录详细的操作日志"""
        timestamp = time.time()
        with self.lock:
            print(f"[{timestamp:.3f}] {thread_name:>10}: {action:<8} | {item:<15} | {details}")
    
    def producer_worker(self, producer_id: int, items_to_produce: int):
        """生产者线程：产生数据并放入共享Map中"""
        thread_name = f"Producer-{producer_id}"
        self.log(thread_name, "START", f"准备生产 {items_to_produce} 个物品")
        
        for i in range(items_to_produce):
            # 模拟生产耗时
            time.sleep(random.uniform(0.01, 0.05))
            
            # 生产物品
            item_id = f"item_{producer_id}_{i}"
            item_data = {
                "id": item_id,
                "producer": producer_id,
                "sequence": i,
                "timestamp": time.time(),
                "data": f"data_from_producer_{producer_id}_batch_{i}"
            }
            
            # 使用原子操作写入共享Map
            self.shared_map[item_id] = item_data
            
            # 记录生产历史
            with self.lock:
                self.produced_items.append(item_id)
                self.total_produced += 1
            
            self.log(thread_name, "PRODUCE", item_id, f"生产物品，序列号: {i}")
            
            # 偶尔检查Map状态
            if i % 10 == 0:
                current_size = len(self.shared_map)
                self.log(thread_name, "CHECK", f"Map大小: {current_size}")
        
        self.log(thread_name, "COMPLETE", f"完成生产 {items_to_produce} 个物品")
    
    def consumer_worker(self, consumer_id: int, max_items: int = None):
        """消费者线程：从共享Map中消费数据"""
        thread_name = f"Consumer-{consumer_id}"
        consumed_count = 0
        
        self.log(thread_name, "START", f"开始消费，最大消费量: {max_items or '无限制'}")
        
        while self.running:
            try:
                # 使用阻塞操作等待物品（如果Map为空）
                # 这里我们使用 popitem 来获取任意物品
                item_id, item_data = self.shared_map.popitem(block=True, timeout=0.5)
                
                # 记录消费历史
                with self.lock:
                    self.consumed_items.append(item_id)
                    self.total_consumed += 1
                consumed_count += 1
                
                self.log(thread_name, "CONSUME", item_id, 
                        f"消费物品，生产者: {item_data['producer']}, 序列: {item_data['sequence']}")
                
                # 检查消费限制
                if max_items and consumed_count >= max_items:
                    break
                    
            except KeyError:
                # Map为空且无阻塞超时，继续等待
                if not self.running:
                    break
                time.sleep(0.01)
        
        self.log(thread_name, "COMPLETE", f"消费完成，共消费: {consumed_count} 个物品")
    
    def batch_consumer_worker(self, consumer_id: int, batch_size: int = 5):
        """批量消费者：每次消费多个物品"""
        thread_name = f"BatchConsumer-{consumer_id}"
        consumed_count = 0
        
        self.log(thread_name, "START", f"开始批量消费，每批大小: {batch_size}")
        
        while self.running and (consumed_count < 50):  # 限制每个批量消费者消费50个物品
            try:
                # 收集一批物品
                batch_items = []
                for _ in range(batch_size):
                    if not self.running:
                        break
                    
                    try:
                        item_id, item_data = self.shared_map.popitem(block=True, timeout=0.2)
                        batch_items.append((item_id, item_data))
                    except KeyError:
                        # 没有更多物品了
                        break
                
                if not batch_items:
                    break
                
                # 批量处理物品
                for item_id, item_data in batch_items:
                    with self.lock:
                        self.consumed_items.append(item_id)
                        self.total_consumed += 1
                    consumed_count += 1
                    
                    self.log(thread_name, "BATCH_CONSUME", item_id,
                            f"批量消费，生产者: {item_data['producer']}")
                
                # 批量处理后暂停一下
                time.sleep(0.1)
                
            except Exception as e:
                self.log(thread_name, "ERROR", f"批量消费异常: {e}")
                break
        
        self.log(thread_name, "COMPLETE", f"批量消费完成，共消费: {consumed_count} 个物品")
    
    def run_test(self, 
                 num_producers: int = 3, 
                 producer_items: int = 20,
                 num_consumers: int = 2,
                 num_batch_consumers: int = 1,
                 test_duration: float = 5.0):
        """运行生产者消费者测试"""
        
        print("=" * 80)
        print("🚀 生产者消费者测试开始")
        print("=" * 80)
        print(f"配置: {num_producers}个生产者，每个生产{producer_items}个物品")
        print(f"      {num_consumers}个普通消费者，{num_batch_consumers}个批量消费者")
        print(f"      测试持续时间: {test_duration}秒")
        print("=" * 80)
        
        # 重置状态
        self.produced_items.clear()
        self.consumed_items.clear()
        self.total_produced = 0
        self.total_consumed = 0
        self.running = True
        
        # 创建线程
        threads = []
        
        # 创建生产者线程
        for i in range(num_producers):
            t = threading.Thread(
                target=self.producer_worker, 
                args=(i, producer_items),
                name=f"Producer-{i}"
            )
            threads.append(t)
        
        # 创建普通消费者线程
        for i in range(num_consumers):
            t = threading.Thread(
                target=self.consumer_worker,
                args=(i, 30),  # 每个消费者最多消费30个物品
                name=f"Consumer-{i}"
            )
            threads.append(t)
        
        # 创建批量消费者线程
        for i in range(num_batch_consumers):
            t = threading.Thread(
                target=self.batch_consumer_worker,
                args=(i, 3),  # 每批消费3个物品
                name=f"BatchConsumer-{i}"
            )
            threads.append(t)
        
        print(f"\n📊 启动 {len(threads)} 个线程...")
        
        # 启动所有线程
        for t in threads:
            t.start()
            time.sleep(0.01)  # 稍微错开启动时间
        
        # 监控线程：显示实时统计
        def monitor():
            start_time = time.time()
            while self.running and (time.time() - start_time) < test_duration:
                time.sleep(1.0)
                current_time = time.time() - start_time
                print(f"\n[监控 {current_time:.1f}秒] 已生产: {self.total_produced}, 已消费: {self.total_consumed}, Map大小: {len(self.shared_map)}")
        
        monitor_thread = threading.Thread(target=monitor, name="Monitor")
        monitor_thread.start()
        
        # 等待测试完成
        time.sleep(test_duration)
        self.running = False
        
        print("⏹️  发送停止信号给所有线程...")        
        print("-" * 80)
        
        # 等待所有线程完成
        for t in threads:
            t.join(timeout=2.0)
        
        monitor_thread.join(timeout=1.0)
        
        # 最终统计和验证
        print("\n" + "=" * 80)
        print("📈 最终统计结果")
        print("=" * 80)
        print(f"生产总数: {self.total_produced}")
        print(f"消费总数: {self.total_consumed}")
        print(f"最终Map大小: {len(self.shared_map)}")
        
        # 验证数据一致性
        self.verify_consistency()
    
    def verify_consistency(self):
        """验证生产和消费的一致性"""
        print("\n🔍 数据一致性验证")
        print("-" * 80)
        
        # 检查是否有重复消费
        consumed_set = set(self.consumed_items)
        if len(consumed_set) != len(self.consumed_items):
            duplicates = len(self.consumed_items) - len(consumed_set)
            print(f"❌ 发现重复消费: {duplicates} 个物品被消费了多次")
        else:
            print("✅ 没有重复消费，所有消费的物品都是唯一的")
        
        # 检查消费的物品是否都在生产列表中
        produced_set = set(self.produced_items)
        invalid_consumptions = consumed_set - produced_set
        if invalid_consumptions:
            print(f"❌ 发现无效消费: {len(invalid_consumptions)} 个物品被消费但从未被生产")
            print(f"   示例: {list(invalid_consumptions)[:5]}")
        else:
            print("✅ 所有消费的物品都来自生产者")
        
        # 检查生产者是否都完成了生产
        total_expected = sum(len(self.produced_items) for _ in range(3))  # 假设3个生产者
        if self.total_produced == total_expected:
            print("✅ 所有生产者都完成了预期的生产任务")
        else:
            print(f"⚠️  生产任务未全部完成: {self.total_produced}/{total_expected}")
        
        # 显示生产和消费的匹配度
        if self.total_produced > 0:
            consumption_rate = self.total_consumed / self.total_produced * 100
            print(f"📊 消费完成率: {consumption_rate:.1f}% ({self.total_consumed}/{self.total_produced})")
        
        # 显示最终Map中剩余的物品
        remaining = self.shared_map.to_dict()
        if remaining:
            print(f"📦 剩余物品: {len(remaining)} 个")
            for k, v in list(remaining.items())[:5]:  # 只显示前5个
                print(f"   {k}: {v['producer']} -> {v['sequence']}")
        else:
            print("📦 Map为空，所有生产物品都被消费")


def run_simple_producer_consumer():
    """运行简单的生产者消费者测试"""
    test = DetailedProducerConsumerTest()
    test.run_test(
        num_producers=2,
        producer_items=15,
        num_consumers=3,
        num_batch_consumers=1,
        test_duration=3.0
    )


def run_stress_producer_consumer():
    """运行压力生产者消费者测试"""
    test = DetailedProducerConsumerTest()
    test.run_test(
        num_producers=5,
        producer_items=50,
        num_consumers=8,
        num_batch_consumers=2,
        test_duration=8.0
    )


if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 简单测试 (推荐用于观察中间过程)")
    print("2. 压力测试 (用于验证高负载下的稳定性)")
    
    choice = input("请选择 (1或2): ").strip()
    
    if choice == "2":
        run_stress_producer_consumer()
    else:
        run_simple_producer_consumer()
    
    print("\n🎉 测试完成!")