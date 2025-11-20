# -*- coding: utf-8 -*-
"""
OKX Calendar Spread套利机会管理器
专门针对OKX交易所的Calendar Spread机会监控和信号生成
"""

import time
import threading
import yaml
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from dataclasses import dataclass

# 导入OKX Calendar Spread模块
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import get_okx_atm_options
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import (
    find_calendar_spread_options, 
    CalendarSpreadOpportunity,
    display_calendar_opportunities
)


@dataclass
class ArbitrageSignalOKX:
    """OKX套利信号数据结构"""
    signal_id: str
    timestamp: datetime
    signal_type: str  # "calendar_spread"
    opportunity: CalendarSpreadOpportunity
    confidence: float  # 0.0-1.0
    market_conditions: Dict[str, Any]
    exchange: str = "OKX"


class CalendarArbitrageManagerOKX:
    """
    OKX Calendar Spread套利机会管理器
    
    功能：
    1. 每5分钟检查一次OKX Calendar Spread机会
    2. 缓存和去重机会
    3. 生成交易信号
    4. 日志记录和监控
    """
    
    def __init__(self, config_path: str = None):
        """
        初始化OKX套利管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.exchange = "OKX"
        self.is_running = False
        self.check_thread = None
        self.last_opportunities = []
        self.signal_history = []
        
        # 先设置日志
        self._setup_logging()
        
        # 再加载配置
        self.config = self._load_config(config_path)
        
        # 检查间隔（秒）
        self.check_interval = self.config.get("manager_settings", {}).get("check_interval_seconds", 300)  # 5分钟
        
        self.logger.info(f"📊 [OKX] Calendar Arbitrage Manager 初始化完成")
        self.logger.info(f"🔄 检查间隔: {self.check_interval}秒")
        self.logger.info(f"🌐 交易所: {self.exchange}")
    
    def _load_config(self, config_path: str = None) -> Dict[str, Any]:
        """加载配置文件"""
        if config_path is None:
            # 尝试多个可能的配置路径
            possible_paths = [
                "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread_okx.yaml",
                "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml",
                "/home/ubuntu/options_trading/qtrade/demo_trade/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
            ]
            
            for path in possible_paths:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f)
                    self.logger.info(f"✅ 配置文件加载: {path}")
                    return config
                except FileNotFoundError:
                    continue
            
            # 如果都找不到，使用默认配置
            return self._get_default_config()
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            return config
        except Exception as e:
            print(f"❌ 配置文件加载失败: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """默认OKX配置"""
        return {
            "iv_criteria": {
                "min_iv_spread": 0.02,
                "iv_spread_threshold_pct": 0.02
            },
            "strike_criteria": {
                "atm_tolerance_pct": 0.03  # OKX使用3%
            },
            "time_pairings": {
                "valid_combinations": [
                    {"short_days": 7, "long_days": 30},
                    {"short_days": 7, "long_days": 45},
                    {"short_days": 14, "long_days": 30},
                    {"short_days": 14, "long_days": 60}
                ],
                "time_tolerance_days": 5
            },
            "market_filters": {
                "liquidity": {
                    "min_bid_price": 0.001,
                    "max_bid_ask_spread_pct": 0.3,  # OKX流动性可能较低
                    "min_open_interest": 0  # OKX OI可能为0
                },
                "price_sanity": {
                    "min_option_price": 0.0005,
                    "max_option_price": 0.5,
                    "max_iv": 2.0
                }
            },
            "search_config": {
                "data_source": "okx",
                "currencies": ["BTC"],
                "option_types": ["C", "P"],
                "max_results": 10,
                "sort_by": "iv_spread",
                "sort_order": "desc"
            },
            "manager_settings": {
                "check_interval_seconds": 300,
                "min_signal_confidence": 0.5,  # OKX可以放宽到0.5
                "max_signal_history": 100
            }
        }
    
    def _setup_logging(self):
        """设置日志"""
        self.logger = logging.getLogger("CalendarArbitrageManagerOKX")
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - [OKX] %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def start_monitoring(self):
        """启动监控"""
        if self.is_running:
            self.logger.warning("⚠️ 管理器已在运行中")
            return
        
        self.is_running = True
        self.check_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.check_thread.start()
        
        self.logger.info("🚀 [OKX] Calendar Arbitrage Manager 启动成功")
        self.logger.info(f"⏰ 将每{self.check_interval}秒检查一次机会")
    
    def stop_monitoring(self):
        """停止监控"""
        if not self.is_running:
            self.logger.warning("⚠️ 管理器未在运行")
            return
        
        self.is_running = False
        if self.check_thread:
            self.check_thread.join(timeout=10)
        
        self.logger.info("🛑 [OKX] Calendar Arbitrage Manager 已停止")
    
    def _monitoring_loop(self):
        """监控循环"""
        self.logger.info("🔄 开始监控循环...")
        
        while self.is_running:
            try:
                # 检查机会
                opportunities = self.check_opportunities()
                
                if opportunities:
                    # 生成交易信号
                    signals = self._generate_signals(opportunities)
                    
                    if signals:
                        self.logger.info(f"📈 发现 {len(signals)} 个交易信号")
                        for signal in signals:
                            self._process_signal(signal)
                else:
                    self.logger.info("📊 当前无OKX Calendar Spread机会")
                
                # 等待下次检查
                time.sleep(self.check_interval)
                
            except Exception as e:
                self.logger.error(f"❌ 监控循环出错: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(60)  # 出错后等待1分钟再继续
    
    def check_opportunities(self) -> List[CalendarSpreadOpportunity]:
        """
        检查OKX Calendar Spread机会
        
        Returns:
            List[CalendarSpreadOpportunity]: 机会列表，如果没有则返回空列表
        """
        try:
            self.logger.info("🔍 [OKX] 开始检查Calendar Spread机会...")
            
            opportunities = []
            
            # 检查每个币种
            for currency in self.config["search_config"]["currencies"]:
                self.logger.info(f"📊 检查 {currency} 的OKX机会...")
                
                # 1. 获取OKX ATM期权
                atm_options = get_okx_atm_options(self.config, currency)
                
                if not atm_options:
                    self.logger.warning(f"⚠️ {currency} 未找到OKX ATM期权")
                    continue
                
                self.logger.info(f"✅ {currency} 找到 {len(atm_options)} 个OKX ATM期权")
                
                # 2. 搜索Calendar Spread机会
                currency_opportunities = find_calendar_spread_options(atm_options, self.config)
                
                if currency_opportunities:
                    opportunities.extend(currency_opportunities)
                    self.logger.info(f"🎯 {currency} 发现 {len(currency_opportunities)} 个机会")
            
            # 3. 去重和筛选
            filtered_opportunities = self._filter_opportunities(opportunities)
            
            # 4. 更新缓存
            self.last_opportunities = filtered_opportunities
            
            if filtered_opportunities:
                self.logger.info(f"✅ [OKX] 总共发现 {len(filtered_opportunities)} 个有效机会")
                # 简要显示机会
                self._log_opportunities_summary(filtered_opportunities)
            else:
                self.logger.info("📊 当前无符合条件的OKX Calendar Spread机会")
            
            return filtered_opportunities
            
        except Exception as e:
            self.logger.error(f"❌ 检查机会时出错: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filter_opportunities(self, opportunities: List[CalendarSpreadOpportunity]) -> List[CalendarSpreadOpportunity]:
        """筛选和去重机会"""
        if not opportunities:
            return []
        
        # 按信号强度和IV价差筛选
        min_confidence = self.config.get("manager_settings", {}).get("min_signal_confidence", 0.5)
        
        filtered = []
        for opp in opportunities:
            confidence = self._calculate_confidence(opp)
            if confidence >= min_confidence:
                filtered.append(opp)
        
        # 去重（基于相似的执行价和到期时间）
        unique_opportunities = self._remove_duplicates(filtered)
        
        return unique_opportunities
    
    def _calculate_confidence(self, opportunity: CalendarSpreadOpportunity) -> float:
        """计算机会的置信度 (0.0-1.0)"""
        confidence = 0.0
        
        # IV价差贡献 (50%) - OKX更重视IV价差
        iv_score = min(opportunity.iv_spread / 0.08, 1.0)  # 8%IV价差 = 满分
        confidence += iv_score * 0.5
        
        # 信号强度贡献 (30%)
        strength_scores = {"WEAK": 0.3, "MODERATE": 0.6, "STRONG": 1.0}
        strength_score = strength_scores.get(opportunity.signal_strength, 0.3)
        confidence += strength_score * 0.3
        
        # 时间间隔贡献 (20%)
        time_score = min(opportunity.time_gap_days / 25, 1.0)  # 25天 = 满分
        confidence += time_score * 0.2
        
        # OKX流动性可能较低，不强制要求
        
        return min(confidence, 1.0)
    
    def _remove_duplicates(self, opportunities: List[CalendarSpreadOpportunity]) -> List[CalendarSpreadOpportunity]:
        """去重相似机会"""
        if len(opportunities) <= 1:
            return opportunities
        
        unique = []
        for opp in opportunities:
            is_duplicate = False
            
            for existing in unique:
                # 检查是否为相似机会（相同执行价范围和相似到期时间）
                strike_diff = abs(opp.short_option.strike - existing.short_option.strike)
                short_time_diff = abs(opp.short_option.days_to_expiry - existing.short_option.days_to_expiry)
                long_time_diff = abs(opp.long_option.days_to_expiry - existing.long_option.days_to_expiry)
                
                if (strike_diff < opp.short_option.strike * 0.02 and  # 2%执行价差异
                    short_time_diff <= 2 and long_time_diff <= 2):  # 2天时间差异
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique.append(opp)
        
        return unique
    
    def _generate_signals(self, opportunities: List[CalendarSpreadOpportunity]) -> List[ArbitrageSignalOKX]:
        """生成交易信号"""
        signals = []
        
        for opp in opportunities:
            confidence = self._calculate_confidence(opp)
            
            signal = ArbitrageSignalOKX(
                signal_id=f"OKX_CAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{opp.rank}",
                timestamp=datetime.now(),
                signal_type="calendar_spread",
                opportunity=opp,
                confidence=confidence,
                market_conditions=self._get_market_conditions(),
                exchange="OKX"
            )
            
            signals.append(signal)
        
        return signals
    
    def _get_market_conditions(self) -> Dict[str, Any]:
        """获取市场条件"""
        return {
            "timestamp": datetime.now().isoformat(),
            "exchange": "OKX",
            "volatility_regime": "normal",  # 可以后续扩展
        }
    
    def _process_signal(self, signal: ArbitrageSignalOKX):
        """处理交易信号"""
        # 记录信号
        self.signal_history.append(signal)
        
        # 限制历史记录数量
        max_history = self.config.get("manager_settings", {}).get("max_signal_history", 100)
        if len(self.signal_history) > max_history:
            self.signal_history = self.signal_history[-max_history:]
        
        # 日志记录
        self.logger.info(f"📈 [OKX] 生成交易信号: {signal.signal_id}")
        self.logger.info(f"   置信度: {signal.confidence:.2%}")
        self.logger.info(f"   IV价差: {signal.opportunity.iv_spread:.1%}")
        self.logger.info(f"   信号强度: {signal.opportunity.signal_strength}")
        
        # TODO: 这里将来可以发送信号给trading engine
        # self._send_signal_to_trader(signal)
    
    def _log_opportunities_summary(self, opportunities: List[CalendarSpreadOpportunity]):
        """记录机会摘要"""
        for i, opp in enumerate(opportunities[:5], 1):  # 显示前5个
            self.logger.info(f"   #{i}: {opp.short_option.symbol} -> {opp.long_option.symbol}")
            self.logger.info(f"       IV价差: {opp.iv_spread:.1%}, 信号: {opp.signal_strength}, Strike: ${opp.short_option.strike:,.0f}")
    
    def get_latest_opportunities(self) -> List[CalendarSpreadOpportunity]:
        """获取最新的机会"""
        return self.last_opportunities.copy()
    
    def get_signal_history(self, limit: int = 10) -> List[ArbitrageSignalOKX]:
        """获取信号历史"""
        return self.signal_history[-limit:]
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        return {
            "is_running": self.is_running,
            "check_interval": self.check_interval,
            "exchange": self.exchange,
            "last_check": datetime.now().isoformat(),
            "opportunities_count": len(self.last_opportunities),
            "signals_count": len(self.signal_history),
            "config_loaded": bool(self.config)
        }


# 便捷函数
def create_okx_manager(config_path: str = None) -> CalendarArbitrageManagerOKX:
    """创建OKX套利管理器"""
    return CalendarArbitrageManagerOKX(config_path=config_path)


if __name__ == "__main__":
    # 测试用例
    print("🚀 [OKX] 启动Calendar Arbitrage Manager测试...")
    
    manager = create_okx_manager()
    
    # 手动检查一次
    opportunities = manager.check_opportunities()
    
    if opportunities:
        print(f"\n✅ [OKX] 发现 {len(opportunities)} 个机会:")
        display_calendar_opportunities(opportunities)
    else:
        print("\n📊 当前无OKX Calendar Spread机会")
    
    print("\n📊 管理器状态:")
    status = manager.get_status()
    for key, value in status.items():
        print(f"   {key}: {value}")
    
    # 如果需要启动持续监控，取消下面的注释
    # print("\n🔄 启动持续监控 (Ctrl+C 停止)...")
    # manager.start_monitoring()
    # try:
    #     while True:
    #         time.sleep(1)
    # except KeyboardInterrupt:
    #     print("\n🛑 收到停止信号...")
    #     manager.stop_monitoring()
    #     print("✅ 管理器已停止")

