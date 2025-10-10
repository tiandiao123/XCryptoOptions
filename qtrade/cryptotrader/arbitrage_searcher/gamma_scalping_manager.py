# -*- coding: utf-8 -*-
"""
Gamma Scalping Manager - Selling Straddle机会监控管理器
基于calendar_spread_manager.py设计，专门用于监控Selling Straddle套利机会
"""

import time
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Any
import logging
from dataclasses import dataclass

# 导入我们的Gamma Scalping模块
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import (
    SellingStraddleFinder,
    StraddleOpportunity
)


@dataclass
class GammaScalpingSignal:
    """Gamma Scalping信号数据结构"""
    signal_id: str
    timestamp: datetime
    signal_type: str  # "selling_straddle"
    opportunity: StraddleOpportunity
    confidence: float  # 0.0-1.0
    market_conditions: Dict[str, Any]


class GammaScalpingManager:
    """
    Gamma Scalping - Selling Straddle套利机会管理器
    
    功能：
    1. 每5分钟检查一次Selling Straddle机会
    2. 缓存和去重机会
    3. 生成交易信号
    4. 日志记录和监控
    """
    
    def __init__(self, config_path: str, env: str = "testnet"):
        """
        初始化Gamma Scalping管理器
        
        Args:
            config_path: 配置文件路径
            env: 交易环境 (testnet/mainnet)
        """
        self.env = env
        self.is_running = False
        self.monitor_thread = None
        self.check_interval = 300  # 5分钟 = 300秒
        
        # 信号缓存
        self.recent_signals: List[GammaScalpingSignal] = []
        self.signal_history: List[GammaScalpingSignal] = []
        self.max_recent_signals = 10  # 最多保留10个最近信号
        
        # 统计信息
        self.total_checks = 0
        self.total_opportunities_found = 0
        self.last_check_time = None
        self.last_opportunity_time = None
        
        # 初始化Selling Straddle寻找器
        self.straddle_finder = SellingStraddleFinder(
            currency="BTC",
            env=self.env,
            config_path=config_path
        )
    
        # 设置日志
        self._setup_logging()
        
        self.logger.info(f"🚀 Gamma Scalping Manager 初始化完成")
        self.logger.info(f"   环境: {env}")
        self.logger.info(f"   检查间隔: {self.check_interval}秒")
    
    def _setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger("GammaScalpingManager")
        self.logger.setLevel(logging.INFO)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def start_monitoring(self):
        """开始监控"""
        if self.is_running:
            self.logger.warning("⚠️ 监控已在运行中")
            return
        
        self.is_running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("🚀 Gamma Scalping监控已启动")
        self.logger.info(f"   检查间隔: {self.check_interval}秒")
    
    def stop_monitoring(self):
        """停止监控"""
        if not self.is_running:
            self.logger.warning("⚠️ 监控未在运行")
            return
        
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)
        
        self.logger.info("🛑 Gamma Scalping监控已停止")
    
    def _monitor_loop(self):
        """监控循环"""
        self.logger.info("🔄 开始监控循环...")
        
        while self.is_running:
            try:
                # 检查机会
                opportunities = self.check_opportunities()
                
                # 生成信号
                if opportunities:
                    signals = self._generate_signals(opportunities)
                    self._process_signals(signals)
                
                # 等待下次检查
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"❌ 监控循环出错: {e}")
                time.sleep(60)  # 出错后等待1分钟再继续
    
    def check_opportunities(self) -> List[StraddleOpportunity]:
        """
        检查Selling Straddle机会
        
        Returns:
            找到的机会列表，如果没有则返回空列表
        """
        self.total_checks += 1
        self.last_check_time = datetime.now()
        
        self.logger.info(f"🔍 第{self.total_checks}次检查Selling Straddle机会...")

        
        # 寻找机会
        opportunities = self.straddle_finder.find_selling_straddle_opportunities()
        
        if opportunities:
            self.total_opportunities_found += len(opportunities)
            self.last_opportunity_time = datetime.now()
            
            self.logger.info(f"✅ 找到 {len(opportunities)} 个Selling Straddle机会")
            
            # 简要显示机会
            for i, opp in enumerate(opportunities, 1):
                self.logger.info(
                    f"   机会{i}: ${opp.strike_price:,.0f} {opp.days_to_expiry}天 "
                    f"IV溢价{opp.iv_premium_pct:+.1f}% 评分{opp.score:.1f}"
                )
            
            return opportunities
        else:
            self.logger.info("📊 当前没有找到合适的Selling Straddle机会")
            return []


    def _generate_signals(self, opportunities: List[StraddleOpportunity]) -> List[GammaScalpingSignal]:
        """生成交易信号"""
        signals = []
        current_time = datetime.now()
        
        for opp in opportunities:
            # 计算信号置信度
            confidence = self._calculate_confidence(opp)
            
            # 收集市场条件
            market_conditions = {
                "spot_price": getattr(opp, 'spot_price', 0),
                "realized_vol": opp.realized_vol,
                "avg_iv": opp.avg_iv,
                "iv_premium": opp.iv_premium,
                "iv_premium_pct": opp.iv_premium_pct,
                "net_delta": opp.net_delta,
                "net_delta_adjusted": opp.net_delta_adjusted,
                "total_gamma": opp.total_gamma,
                "total_theta": opp.total_theta,
                "signal_strength": opp.signal_strength
            }
            
            # 生成信号ID
            signal_id = f"straddle_{opp.strike_price}_{opp.days_to_expiry}_{current_time.strftime('%Y%m%d_%H%M%S')}"
            
            signal = GammaScalpingSignal(
                signal_id=signal_id,
                timestamp=current_time,
                signal_type="selling_straddle",
                opportunity=opp,
                confidence=confidence,
                market_conditions=market_conditions
            )
            
            signals.append(signal)
        
        return signals
    
    def _calculate_confidence(self, opportunity: StraddleOpportunity) -> float:
        """计算信号置信度"""
        confidence = 0.0
        
        # 基于评分
        confidence += min(opportunity.score / 100, 0.4)  # 最多0.4
        
        # 基于IV溢价
        if opportunity.iv_premium_pct > 20:
            confidence += 0.3
        elif opportunity.iv_premium_pct > 10:
            confidence += 0.2
        elif opportunity.iv_premium_pct > 5:
            confidence += 0.1
        
        # 基于信号强度
        strength_bonus = {
            "STRONG": 0.3,
            "MEDIUM": 0.2,
            "WEAK": 0.1
        }
        confidence += strength_bonus.get(opportunity.signal_strength, 0)
        
        return min(confidence, 1.0)
    
    def _process_signals(self, signals: List[GammaScalpingSignal]):
        """处理信号"""
        for signal in signals:
            # 检查是否重复
            if not self._is_duplicate_signal(signal):
                # 添加到缓存
                self.recent_signals.append(signal)
                self.signal_history.append(signal)
                
                # 限制缓存大小
                if len(self.recent_signals) > self.max_recent_signals:
                    self.recent_signals.pop(0)
                
                # 记录信号
                self.logger.info(f"🎯 新信号: {signal.signal_id}")
                self.logger.info(f"   置信度: {signal.confidence:.2f}")
                self.logger.info(f"   执行价: ${signal.opportunity.strike_price:,.0f}")
                self.logger.info(f"   IV溢价: {signal.opportunity.iv_premium_pct:+.1f}%")
    
    def _is_duplicate_signal(self, new_signal: GammaScalpingSignal) -> bool:
        """检查是否为重复信号"""
        # 检查最近1小时内是否有相同执行价和到期日的信号
        cutoff_time = datetime.now() - timedelta(hours=1)
        
        for recent_signal in self.recent_signals:
            if (recent_signal.timestamp > cutoff_time and
                recent_signal.opportunity.strike_price == new_signal.opportunity.strike_price and
                recent_signal.opportunity.days_to_expiry == new_signal.opportunity.days_to_expiry):
                return True
        
        return False
    
    def get_recent_signals(self, hours: int = 24) -> List[GammaScalpingSignal]:
        """获取最近的信号"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [s for s in self.signal_history if s.timestamp > cutoff_time]
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        recent_signals = self.get_recent_signals(24)
        
        return {
            "total_checks": self.total_checks,
            "total_opportunities_found": self.total_opportunities_found,
            "recent_signals_24h": len(recent_signals),
            "last_check_time": self.last_check_time,
            "last_opportunity_time": self.last_opportunity_time,
            "is_running": self.is_running,
            "check_interval_seconds": self.check_interval,
            "success_rate": (
                self.total_opportunities_found / max(self.total_checks, 1) * 100
            )
        }
    
    def print_status(self):
        """打印当前状态"""
        stats = self.get_statistics()
        recent_signals = self.get_recent_signals(24)
        
        print(f"\n📊 Gamma Scalping Manager 状态报告")
        print(f"="*60)
        print(f"🔄 运行状态: {'运行中' if stats['is_running'] else '已停止'}")
        print(f"🔍 总检查次数: {stats['total_checks']}")
        print(f"🎯 总机会数: {stats['total_opportunities_found']}")
        print(f"📈 成功率: {stats['success_rate']:.1f}%")
        print(f"⏰ 检查间隔: {stats['check_interval_seconds']}秒")
        
        if stats['last_check_time']:
            print(f"🕐 最后检查: {stats['last_check_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        if stats['last_opportunity_time']:
            print(f"🎯 最后机会: {stats['last_opportunity_time'].strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"📊 24小时信号: {stats['recent_signals_24h']}个")
        
        if recent_signals:
            print(f"\n🎯 最近信号:")
            for signal in recent_signals[-5:]:  # 显示最近5个
                print(f"   {signal.timestamp.strftime('%H:%M:%S')} - "
                      f"${signal.opportunity.strike_price:,.0f} "
                      f"({signal.opportunity.days_to_expiry}天) "
                      f"置信度{signal.confidence:.2f}")


# 测试函数
def test_gamma_scalping_manager():
    """测试Gamma Scalping Manager"""
    
    print("🚀 Gamma Scalping Manager 测试")
    print("="*60)
    
    # 初始化管理器
    manager = GammaScalpingManager(config_path="/home/ubuntu/options_trading/qtrade/cryptotrader/arbitrage_searcher/gamma_scalping/selling_straddle.yaml",
                                    env="testnet")
    
    # 测试单次检查
    print("\n🔍 测试单次机会检查...")
    opportunities = manager.check_opportunities()
    
    if opportunities:
        print(f"✅ 找到 {len(opportunities)} 个机会")
        
        # 生成信号
        signals = manager._generate_signals(opportunities)
        manager._process_signals(signals)
        
    else:
        print("📊 当前没有机会")
    
    # 显示状态
    manager.print_status()
    
    # 询问是否开始监控
    print(f"\n💡 如需开始5分钟监控，请运行:")
    print(f"   manager.start_monitoring()")
    print(f"   # 运行一段时间后...")
    print(f"   manager.stop_monitoring()")
        


if __name__ == "__main__":
    test_gamma_scalping_manager()
