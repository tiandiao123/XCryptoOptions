# -*- coding: utf-8 -*-
"""
EWMA波动率跟踪器实时测试
1分钟级别定时更新实验，验证系统是否能正常工作
"""

import sys
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path

from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.ewma_vol_tracker import RealDataEWMAVolTracker

# 添加项目路径
sys.path.append('/home/ubuntu/options_trading')



class RealTimeVolTrackerTest:
    """实时波动率跟踪器测试类"""
    
    def __init__(self, symbol: str = "BTCUSDT", interval: str = "1m", window_size: int = 60):
        """
        初始化实时测试
        
        Args:
            symbol: 交易对
            interval: 时间间隔
            window_size: 窗口大小 (60个1分钟 = 1小时)
        """
        self.symbol = symbol
        self.interval = interval
        self.window_size = window_size
        self.is_running = False
        self.update_thread = None
        self.vol_tracker = None
        self.update_count = 0
        self.start_time = None
        
        print(f"🚀 初始化实时波动率跟踪器测试")
        print(f"   交易对: {symbol}")
        print(f"   时间间隔: {interval}")
        print(f"   窗口大小: {window_size}")
        print(f"   测试目标: 验证1分钟定时更新功能")
    
    def initialize_tracker(self) -> bool:
        """初始化波动率跟踪器"""
        try:
            print(f"\n📊 初始化{self.interval}波动率跟踪器...")
            
            self.vol_tracker = RealDataEWMAVolTracker(
                symbol=self.symbol,
                interval=self.interval,
                window_size=self.window_size,
                ewma_lambda=0.94
            )
            
            if self.vol_tracker.is_initialized:
                print(f"✅ 波动率跟踪器初始化成功")
                
                # 显示初始状态
                status = self.vol_tracker.get_status()
                print(f"📊 初始状态:")
                print(f"   数据点: {status['data_points']}")
                print(f"   最新价格: ${status['latest_price']:,.2f}")
                print(f"   年化因子: {status['annualization_factor']:.0f}")
                
                # 显示CSV验证
                self.vol_tracker.print_csv_summary()
                
                return True
            else:
                print(f"❌ 波动率跟踪器初始化失败")
                return False
                
        except Exception as e:
            print(f"❌ 初始化失败: {e}")
            return False
    
    def update_volatility(self):
        """更新波动率数据"""
        try:
            print(f"\n🔄 第{self.update_count + 1}次更新 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            # 调用predict方法，会自动检查并更新最新数据
            result = self.vol_tracker.predict()
            
            if result['success']:
                self.update_count += 1
                
                print(f"✅ 更新成功:")
                print(f"   年化波动率: {result['realized_vol_annualized']:.1%}")
                print(f"   日波动率: {result['realized_vol_daily']:.1%}")
                print(f"   最新价格: ${result['latest_price']:,.2f}")
                print(f"   有新数据: {'是' if result['has_new_data'] else '否'}")
                print(f"   数据点数: {result['data_points']}")
                
                # 显示运行统计
                elapsed = datetime.now() - self.start_time
                print(f"   运行时长: {elapsed}")
                print(f"   更新次数: {self.update_count}")
                
                # 每5次更新显示一次CSV验证
                if self.update_count % 5 == 0:
                    print(f"\n📋 第{self.update_count}次更新后的CSV状态:")
                    self.vol_tracker.print_csv_summary()
                    
                    # 显示最新几条记录
                    print(f"\n📄 CSV最新3条记录:")
                    csv_tail = self.vol_tracker.get_csv_tail(3)
                    if not csv_tail.empty:
                        for _, row in csv_tail.iterrows():
                            print(f"   {row['datetime']} | ${row['close']:,.2f}")
                
                # 检查波动率合理性
                vol = result['realized_vol_annualized']
                if vol < 0.05 or vol > 3.0:  # 5%-300%
                    print(f"   ⚠️ 波动率异常: {vol:.1%}")
                
            else:
                print(f"❌ 更新失败: {result['error']}")
                
        except Exception as e:
            print(f"❌ 更新过程出错: {e}")
    
    def update_loop(self):
        """更新循环"""
        print(f"\n🔄 开始1分钟定时更新循环...")
        
        while self.is_running:
            try:
                self.update_volatility()
                
                # 等待1分钟 (60秒)
                if self.is_running:
                    print(f"⏳ 等待60秒后进行下次更新...")
                    time.sleep(60)
                    
            except KeyboardInterrupt:
                print(f"\n⚠️ 收到中断信号，停止更新...")
                break
            except Exception as e:
                print(f"❌ 更新循环出错: {e}")
                time.sleep(10)  # 出错后等待10秒再继续
    
    def start_realtime_test(self, duration_minutes: int = 10):
        """
        开始实时测试
        
        Args:
            duration_minutes: 测试持续时间(分钟)
        """
        try:
            print(f"\n🎯 开始{duration_minutes}分钟实时测试...")
            
            self.start_time = datetime.now()
            self.is_running = True
            
            # 启动更新线程
            self.update_thread = threading.Thread(target=self.update_loop, daemon=True)
            self.update_thread.start()
            
            # 主线程等待指定时间
            end_time = self.start_time + timedelta(minutes=duration_minutes)
            
            while datetime.now() < end_time and self.is_running:
                remaining = end_time - datetime.now()
                print(f"\n⏰ 剩余测试时间: {remaining}")
                time.sleep(30)  # 每30秒显示一次剩余时间
            
            # 停止测试
            self.stop_test()
            
        except KeyboardInterrupt:
            print(f"\n⚠️ 用户中断测试")
            self.stop_test()
        except Exception as e:
            print(f"❌ 测试过程出错: {e}")
            self.stop_test()
    
    def stop_test(self):
        """停止测试"""
        print(f"\n🛑 停止实时测试...")
        self.is_running = False
        
        if self.update_thread and self.update_thread.is_alive():
            self.update_thread.join(timeout=5)
        
        # 显示最终统计
        if self.start_time:
            total_time = datetime.now() - self.start_time
            print(f"\n📊 测试完成统计:")
            print(f"   总运行时间: {total_time}")
            print(f"   总更新次数: {self.update_count}")
            print(f"   平均更新间隔: {total_time.total_seconds() / max(1, self.update_count):.1f}秒")
        
        # 最终CSV验证
        if self.vol_tracker:
            print(f"\n📋 最终CSV验证:")
            self.vol_tracker.print_csv_summary()
    
    def continuous_update_test(self, total_updates: int = 10):
        """
        连续更新测试 - 每分钟更新一次，验证时间连续性
        
        Args:
            total_updates: 总更新次数
        """
        try:
            print(f"\n🔄 连续更新测试: {total_updates}次更新 (每60秒一次)")
            print(f"目标: 验证时间点连续性和数据完整性")
            
            self.start_time = datetime.now()
            previous_timestamp = None
            
            for i in range(total_updates):
                update_start = datetime.now()
                print(f"\n{'='*60}")
                print(f"📊 第{i+1}/{total_updates}次更新 - {update_start.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 调用predict方法更新数据
                result = self.vol_tracker.predict()
                
                if result['success']:
                    current_price = result['latest_price']
                    has_new_data = result['has_new_data']
                    
                    print(f"✅ 更新成功:")
                    print(f"   最新价格: ${current_price:,.2f}")
                    print(f"   年化波动率: {result['realized_vol_annualized']:.1%}")
                    print(f"   有新数据: {'是' if has_new_data else '否'}")
                    
                    # 获取最新的CSV记录来检查时间连续性
                    csv_tail = self.vol_tracker.get_csv_tail(3)
                    if not csv_tail.empty:
                        latest_record = csv_tail.iloc[-1]
                        current_timestamp = latest_record['datetime']
                        
                        print(f"   CSV最新时间: {current_timestamp}")
                        
                        # 检查时间连续性
                        if previous_timestamp and has_new_data:
                            prev_dt = datetime.strptime(previous_timestamp, '%Y-%m-%d %H:%M:%S')
                            curr_dt = datetime.strptime(current_timestamp, '%Y-%m-%d %H:%M:%S')
                            time_diff = (curr_dt - prev_dt).total_seconds() / 60  # 分钟差
                            
                            print(f"   时间间隔: {time_diff:.1f}分钟")
                            
                            if abs(time_diff - 1.0) < 0.1:  # 允许0.1分钟误差
                                print(f"   ✅ 时间连续性: 正常")
                            else:
                                print(f"   ⚠️ 时间连续性: 异常 (期望1分钟，实际{time_diff:.1f}分钟)")
                        
                        # 更新前一个时间戳
                        if has_new_data:
                            previous_timestamp = current_timestamp
                        
                        # 显示最近3条记录
                        print(f"   📄 最近3条记录:")
                        for _, row in csv_tail.iterrows():
                            print(f"      {row['datetime']} | ${row['close']:,.2f}")
                    
                else:
                    print(f"❌ 更新失败: {result['error']}")
                
                # 计算下次更新时间
                if i < total_updates - 1:  # 不是最后一次
                    elapsed = (datetime.now() - update_start).total_seconds()
                    sleep_time = max(0, 60 - elapsed)  # 确保总间隔是60秒
                    
                    next_update = datetime.now() + timedelta(seconds=sleep_time)
                    print(f"⏳ 等待{sleep_time:.1f}秒，下次更新: {next_update.strftime('%H:%M:%S')}")
                    
                    time.sleep(sleep_time)
            
            # 最终验证
            print(f"\n{'='*60}")
            print(f"📊 连续更新测试完成!")
            
            total_time = datetime.now() - self.start_time
            print(f"   总耗时: {total_time}")
            print(f"   平均间隔: {total_time.total_seconds() / total_updates:.1f}秒")
            
            # 验证CSV数据的时间连续性
            self._verify_time_continuity()
            
        except Exception as e:
            print(f"❌ 连续更新测试失败: {e}")
    
    def _verify_time_continuity(self):
        """验证CSV数据的时间连续性"""
        try:
            print(f"\n🔍 验证CSV时间连续性...")
            
            if not self.vol_tracker.csv_file.exists():
                print(f"❌ CSV文件不存在")
                return
            
            import pandas as pd
            df = pd.read_csv(self.vol_tracker.csv_file)
            
            if len(df) < 2:
                print(f"⚠️ 数据不足，无法验证连续性")
                return
            
            # 转换时间戳并计算间隔
            df['timestamp_dt'] = pd.to_datetime(df['timestamp_ms'], unit='ms')
            df = df.sort_values('timestamp_dt')
            
            time_diffs = df['timestamp_dt'].diff().dt.total_seconds() / 60  # 分钟
            time_diffs = time_diffs.dropna()
            
            # 统计时间间隔
            expected_interval = 1  # 1分钟
            correct_intervals = (abs(time_diffs - expected_interval) < 0.1).sum()
            total_intervals = len(time_diffs)
            accuracy = (correct_intervals / total_intervals * 100) if total_intervals > 0 else 0
            
            print(f"   📊 时间连续性统计:")
            print(f"      总间隔数: {total_intervals}")
            print(f"      正确间隔: {correct_intervals}")
            print(f"      准确率: {accuracy:.1f}%")
            
            # 显示异常间隔
            abnormal_intervals = time_diffs[abs(time_diffs - expected_interval) >= 0.1]
            if len(abnormal_intervals) > 0:
                print(f"   ⚠️ 异常时间间隔:")
                for i, interval in enumerate(abnormal_intervals.head(5)):
                    print(f"      #{i+1}: {interval:.1f}分钟")
            else:
                print(f"   ✅ 所有时间间隔都正常")
            
            # 显示时间范围
            start_time = df.iloc[0]['datetime']
            end_time = df.iloc[-1]['datetime']
            print(f"   ⏰ 数据时间范围: {start_time} 到 {end_time}")
            
        except Exception as e:
            print(f"❌ 时间连续性验证失败: {e}")


def main():
    """主函数"""
    print("="*80)
    print("🧪 EWMA波动率跟踪器实时测试")
    print("="*80)
    
    # 创建测试实例
    test = RealTimeVolTrackerTest(
        symbol="BTCUSDT",
        interval="1m",
        window_size=60 * 24  # 60个1分钟 = 1小时数据 (避免超过1000的问题)
    )
    
    # 初始化
    if not test.initialize_tracker():
        print("❌ 初始化失败，退出测试")
        return
    
    # 选择测试模式
    print(f"\n📋 自动运行连续更新测试:")
    print(f"   模式: 连续更新测试 (5次更新，每60秒一次)")
    print(f"   目标: 验证时间点连续性")
    
    try:
        # 运行连续更新测试
        test.continuous_update_test(5)
            
    except KeyboardInterrupt:
        print(f"\n⚠️ 用户中断")
    except Exception as e:
        print(f"❌ 测试出错: {e}")
    finally:
        test.stop_test()
    
    print(f"\n✅ 测试结束!")


if __name__ == "__main__":
    main()
