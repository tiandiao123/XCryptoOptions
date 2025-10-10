#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar Arbitrage Manager 监测测试脚本
运行一周，监测是否能发现Calendar Spread机会
"""

import sys
import os
import time
import json
from datetime import datetime, timedelta
from pathlib import Path

from qtrade.cryptotrader.arbitrage_searcher.calendar_spread_manager import CalendarArbitrageManager

# 添加项目路径
project_root = Path(__file__).parent.parent.parent
sys.path.append(str(project_root))



class WeeklyMonitor:
    """一周监测器"""
    
    def __init__(self, output_file="calendar_monitor_results.json"):
        self.output_file = output_file
        self.results = []
        self.start_time = datetime.now()
        self.manager = CalendarArbitrageManager(env="testnet")
        
        print(f"🚀 开始一周监测测试")
        print(f"📅 开始时间: {self.start_time}")
        print(f"💾 结果保存至: {self.output_file}")
        print("=" * 60)
    
    def run_weekly_test(self):
        """运行一周测试"""
        try:
            # 设置结束时间（7天后）
            end_time = self.start_time + timedelta(days=7)
            check_count = 0
            opportunities_found = 0
            
            print(f"⏰ 将运行至: {end_time}")
            print(f"🔄 每5分钟检查一次...")
            print()
            
            while datetime.now() < end_time:
                check_count += 1
                current_time = datetime.now()
                
                print(f"🔍 第{check_count}次检查 - {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 检查机会
                opportunities = self.manager.check_opportunities()
                
                # 记录结果
                result = {
                    "check_number": check_count,
                    "timestamp": current_time.isoformat(),
                    "opportunities_count": len(opportunities) if opportunities else 0,
                    "opportunities": []
                }
                
                if opportunities:
                    opportunities_found += len(opportunities)
                    print(f"✅ 发现 {len(opportunities)} 个机会!")
                    
                    for i, opp in enumerate(opportunities, 1):
                        opp_data = {
                            "rank": i,
                            "short_option": {
                                "symbol": opp.short_option.symbol,
                                "strike": opp.short_option.strike,
                                "days_to_expiry": opp.short_option.days_to_expiry,
                                "iv": opp.short_option.iv,
                                "mid_price": opp.short_option.mid_price
                            },
                            "long_option": {
                                "symbol": opp.long_option.symbol,
                                "strike": opp.long_option.strike,
                                "days_to_expiry": opp.long_option.days_to_expiry,
                                "iv": opp.long_option.iv,
                                "mid_price": opp.long_option.mid_price
                            },
                            "iv_spread": opp.iv_spread,
                            "signal_strength": opp.signal_strength,
                            "net_premium": opp.net_premium,
                            "time_gap_days": opp.time_gap_days
                        }
                        result["opportunities"].append(opp_data)
                        
                        print(f"   #{i}: {opp.short_option.symbol} -> {opp.long_option.symbol}")
                        print(f"       IV价差: {opp.iv_spread:.1%}, 强度: {opp.signal_strength}")
                else:
                    print("📊 无机会")
                
                # 保存结果
                self.results.append(result)
                self._save_results()
                
                # 显示统计
                elapsed = current_time - self.start_time
                remaining = end_time - current_time
                print(f"📈 统计: 总检查{check_count}次, 发现机会{opportunities_found}个")
                print(f"⏱️  已运行: {self._format_duration(elapsed)}, 剩余: {self._format_duration(remaining)}")
                print("-" * 60)
                
                # 等待5分钟
                time.sleep(300)  # 5分钟 = 300秒
            
            # 最终统计
            self._print_final_stats(check_count, opportunities_found)
            
        except KeyboardInterrupt:
            print("\n⚠️ 用户中断测试")
            self._print_final_stats(check_count, opportunities_found)
        except Exception as e:
            print(f"❌ 测试出错: {e}")
            self._save_results()
    
    def _save_results(self):
        """保存结果到文件"""
        try:
            with open(self.output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "test_info": {
                        "start_time": self.start_time.isoformat(),
                        "last_update": datetime.now().isoformat(),
                        "total_checks": len(self.results),
                        "total_opportunities": sum(r["opportunities_count"] for r in self.results)
                    },
                    "results": self.results
                }, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"⚠️ 保存结果失败: {e}")
    
    def _format_duration(self, duration):
        """格式化时间间隔"""
        total_seconds = int(duration.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        
        if days > 0:
            return f"{days}天{hours}小时{minutes}分钟"
        elif hours > 0:
            return f"{hours}小时{minutes}分钟"
        else:
            return f"{minutes}分钟"
    
    def _print_final_stats(self, check_count, opportunities_found):
        """打印最终统计"""
        print("\n" + "=" * 60)
        print("📊 一周监测测试完成!")
        print("=" * 60)
        
        end_time = datetime.now()
        total_duration = end_time - self.start_time
        
        print(f"⏰ 测试时间: {self.start_time.strftime('%Y-%m-%d %H:%M')} -> {end_time.strftime('%Y-%m-%d %H:%M')}")
        print(f"⏱️  总时长: {self._format_duration(total_duration)}")
        print(f"🔍 总检查次数: {check_count}")
        print(f"✅ 发现机会总数: {opportunities_found}")
        
        if check_count > 0:
            success_rate = (opportunities_found / check_count) * 100
            print(f"📈 机会发现率: {success_rate:.1f}% ({opportunities_found}/{check_count})")
        
        # 分析结果
        if opportunities_found > 0:
            opportunities_per_day = opportunities_found / max(1, total_duration.days)
            print(f"📊 平均每天发现: {opportunities_per_day:.1f} 个机会")
            
            # 找出最好的机会
            best_iv_spread = 0
            best_opportunity = None
            
            for result in self.results:
                for opp in result["opportunities"]:
                    if opp["iv_spread"] > best_iv_spread:
                        best_iv_spread = opp["iv_spread"]
                        best_opportunity = opp
            
            if best_opportunity:
                print(f"🏆 最佳机会:")
                print(f"   时间: {best_opportunity.get('timestamp', 'Unknown')}")
                print(f"   IV价差: {best_iv_spread:.1%}")
                print(f"   强度: {best_opportunity['signal_strength']}")
        else:
            print("⚠️ 整周未发现任何机会")
        
        print(f"💾 详细结果已保存至: {self.output_file}")
        print("=" * 60)


def run_quick_test():
    """快速测试（检查几次就结束）"""
    print("🚀 快速测试模式 - 检查3次")
    
    manager = CalendarArbitrageManager(env="testnet")
    
    for i in range(3):
        print(f"\n🔍 第{i+1}次检查...")
        opportunities = manager.check_opportunities()
        
        if opportunities:
            print(f"✅ 发现 {len(opportunities)} 个机会!")
            for j, opp in enumerate(opportunities, 1):
                print(f"   #{j}: IV价差 {opp.iv_spread:.1%}, 强度: {opp.signal_strength}")
        else:
            print("📊 无机会")
        
        if i < 2:  # 不是最后一次
            print("⏳ 等待30秒...")
            time.sleep(30)
    
    print("\n✅ 快速测试完成!")


if __name__ == "__main__":
    print("Calendar Arbitrage Manager 监测测试")
    print("=" * 60)
    
    # 检查命令行参数
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        run_quick_test()
    else:
        print("选择测试模式:")
        print("1. 一周完整监测 (默认)")
        print("2. 快速测试 (3次检查)")
        
        choice = input("\n请选择 (1/2): ").strip()
        
        if choice == "2":
            run_quick_test()
        else:
            monitor = WeeklyMonitor()
            monitor.run_weekly_test()
