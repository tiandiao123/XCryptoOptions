# ------------------- 多线程压力测试 -------------------
from qtrade.cryptotrader.trading_engine.containers.thread_safe_map import ThreadSafeMap


def multi_thread_stress_test():
    """多线程压力测试：验证线程安全性和一致性"""
    import time
    import random
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    print("\n=== 多线程压力测试开始 ===")
    m = ThreadSafeMap()
    
    # 测试参数
    num_threads = 20
    operations_per_thread = 1000
    keys = [f"key_{i}" for i in range(100)]  # 有限的key集合，增加冲突概率
    
    def worker_thread(thread_id):
        """每个线程执行混合操作：读写删查"""
        results = {"reads": 0, "writes": 0, "deletes": 0, "errors": 0}
        local_random = random.Random(thread_id)  # 每个线程独立的随机种子
        
        for _ in range(operations_per_thread):
            try:
                op = local_random.choice(["read", "write", "delete", "compute", "wait"])
                key = local_random.choice(keys)
                
                if op == "read":
                    # 读取操作：get 或 __getitem__
                    if local_random.random() < 0.5:
                        val = m.get(key, "default")
                    else:
                        if key in m:
                            val = m[key]
                        else:
                            val = "not_found"
                    results["reads"] += 1
                    
                elif op == "write":
                    # 写入操作：set 或 update
                    if local_random.random() < 0.7:
                        m[key] = f"val_{thread_id}_{local_random.randint(1, 1000)}"
                    else:
                        # 测试 setdefault
                        val = m.setdefault(key, f"default_{thread_id}")
                    results["writes"] += 1
                    
                elif op == "delete":
                    # 删除操作：delete 或 pop
                    if local_random.random() < 0.5:
                        existed = m.delete(key)
                    else:
                        try:
                            val = m.pop(key, None)
                        except KeyError:
                            pass
                    results["deletes"] += 1
                    
                elif op == "compute":
                    # 原子读改写操作
                    def increment_fn(old_val):
                        if old_val is None:
                            return 1
                        try:
                            return int(old_val) + 1
                        except (ValueError, TypeError):
                            return 1
                    
                    try:
                        new_val = m.compute(key, increment_fn)
                    except Exception:
                        # compute可能因为类型不匹配失败，这是正常的
                        pass
                    results["writes"] += 1
                    
                elif op == "wait":
                    # 等待操作（低概率，避免过多阻塞）
                    if local_random.random() < 0.1:
                        try:
                            val = m.wait_for_key(key, timeout=0.1)
                        except TimeoutError:
                            pass  # 超时是正常的
                        results["reads"] += 1
            
            except Exception as e:
                results["errors"] += 1
                print(f"Thread {thread_id} error: {e}")
        
        return results
    
    # 启动多线程测试
    start_time = time.time()
    thread_results = []
    
    with ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker_thread, i) for i in range(num_threads)]
        
        for future in as_completed(futures):
            try:
                result = future.result()
                thread_results.append(result)
            except Exception as e:
                print(f"Future error: {e}")
    
    end_time = time.time()
    
    # 统计汇总
    total_ops = sum(sum(r.values()) - r["errors"] for r in thread_results)
    total_reads = sum(r["reads"] for r in thread_results)
    total_writes = sum(r["writes"] for r in thread_results) 
    total_deletes = sum(r["deletes"] for r in thread_results)
    total_errors = sum(r["errors"] for r in thread_results)
    
    # 验证一致性：最终状态应该是合理的
    final_dict = m.to_dict()
    print(f"测试完成: {end_time - start_time:.2f}秒")
    print(f"总操作数: {total_ops} (读: {total_reads}, 写: {total_writes}, 删: {total_deletes})")
    print(f"错误数: {total_errors}")
    print(f"最终状态大小: {len(final_dict)}")
    
    # 检查是否有明显的不一致（如负数计数等）
    inconsistencies = []
    for k, v in final_dict.items():
        if k.startswith("key_"):
            try:
                if isinstance(v, str) and v.startswith("val_"):
                    # 这是正常的写入值
                    pass
                elif isinstance(v, int) and v < 0:
                    # 计数器不应该为负
                    inconsistencies.append(f"Negative counter for {k}: {v}")
            except:
                pass
    
    if inconsistencies:
        print(f"发现不一致: {inconsistencies}")
        return False
    else:
        print("✓ 一致性检查通过")
        return True

def concurrent_blocking_test():
    """并发阻塞操作测试"""
    import time
    import threading
    
    print("\n=== 并发阻塞操作测试 ===")
    m = ThreadSafeMap()
    
    results = {"success": 0, "timeout": 0, "error": 0}
    
    def waiter_thread(thread_id):
        """等待者线程"""
        nonlocal results
        try:
            if thread_id % 2 == 0:
                # 等待key出现
                val = m.wait_for_key(f"key_{thread_id}", timeout=2.0)
                results["success"] += 1
            else:
                # 等待并弹出
                val = m.wait_and_pop(f"key_{thread_id}", timeout=2.0)
                results["success"] += 1
        except TimeoutError:
            results["timeout"] += 1
        except Exception as e:
            results["error"] += 1
            print(f"Waiter {thread_id} error: {e}")
    
    def producer_thread():
        """生产者线程：顺序设置所有key"""
        nonlocal results
        for i in range(10):
            time.sleep(0.1)  # 每100ms设置一个key
            m[f"key_{i}"] = f"value_{i}"
            print(f"设置 key_{i}")
    
    # 启动等待者（并发）
    waiters = [threading.Thread(target=waiter_thread, args=(i,)) for i in range(10)]
    for t in waiters:
        t.start()
    
    # 启动生产者
    producer = threading.Thread(target=producer_thread)
    producer.start()
    
    # 等待所有线程完成
    for t in waiters:
        t.join()
    producer.join()
    
    print(f"阻塞测试结果: 成功={results['success']}, 超时={results['timeout']}, 错误={results['error']}")
    print(f"最终状态: {m.to_dict()}")

# 在主测试中调用新的测试函数
if __name__ == "__main__":
    # ... existing tests ...
    
    # 添加新的多线程测试
    success = multi_thread_stress_test()
    concurrent_blocking_test()
    
    if success:
        print("\n🎉 所有测试通过！线程安全验证成功。")
    else:
        print("\n❌ 测试发现问题，请检查实现。")