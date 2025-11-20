#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Options Trading Risk Manager
专为 OKX 交易所设计的风险管理模块
"""

from collections import deque
import time
from typing import Any, Dict, Union, Tuple, Optional
import logging
import requests

from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.ewma_vol_tracker import RealDataEWMAVolTracker
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import CalendarSpreadOpportunity, update_calendar_spread_opportunity
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder_okx import StraddleOpportunityOKX
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder_okx import update_straddle_opportunity_okx
from qtrade.optionstrader.trading_engine.containers.thread_safe_map import ThreadSafeMap

# OKX API clients
from qtrade.order_api.okx.client.options_client import OKXOptionsClient
# Perp 相关函数将延迟导入


class OKXRiskManager:
    """
    OKX 期权交易风险管理器
    
    功能：
    - 持仓管理（添加/移除/查询）
    - 风险监控（止损/止盈/IV反转/价格变化）
    - Delta对冲（使用永续合约）
    - P&L跟踪
    """
    
    def __init__(self, 
                 symbol: str = "BTCUSDT",
                 max_positions: int = 1, 
                 enable_delta_hedge: bool = False, 
                 delta_hedge_threshold: float = 0.05,
                 delta_risk_threshold: float = 0.5,
                 hedge_freq: int = 5,
                 stop_loss_ratio: float = -0.3, 
                 profit_target_ratio: float = 0.5, 
                 price_change_risk_ratio: float = 0.15, 
                 realized_vol_level: str = "30m", 
                 env: str = "testnet"): 
        """
        初始化 OKX 风险管理器
        
        Args:
            symbol: 交易对符号 (e.g., "BTCUSDT")
            max_positions: 最大持仓数量
            enable_delta_hedge: 是否启用Delta对冲
            delta_hedge_threshold: Delta对冲阈值
            delta_risk_threshold: Delta风险阈值
            hedge_freq: 对冲频率（监控周期的倍数，例如5表示每5个监控周期执行一次对冲检查）
            stop_loss_ratio: 止损百分比
            profit_target_ratio: 止盈百分比
            price_change_risk_ratio: 价格变化风险阈值
            realized_vol_level: 实现波动率级别
            env: 交易环境 ('testnet' 或 'mainnet')
        """

        self.max_positions = max_positions
        self.enable_delta_hedge = enable_delta_hedge
        self.delta_risk_threshold = delta_risk_threshold
        self.delta_hedge_threshold = delta_hedge_threshold
        self.hedge_freq = hedge_freq
        self.hedge_counter = 0  # 对冲计数器
        self.current_hedged_delta = 0.0
        self.stop_loss_ratio = stop_loss_ratio
        self.profit_target_ratio = profit_target_ratio
        self.price_change_risk_ratio = price_change_risk_ratio
        self.realized_vol_level = realized_vol_level
        self.env = env

        # 初始化日志记录器
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        # 持仓容器
        self.straddle_positions = ThreadSafeMap()
        self.calendar_spread_positions = ThreadSafeMap()

        # 🆕 永续合约 Realized P&L 跟踪
        self.perp_pnl_dict = {}  # {tradeId: fill_data}
        self.total_perp_realized_pnl = 0.0  # 累积的已实现P&L
        self.last_perp_fill_time = None  # 最后一次成交时间（毫秒时间戳）
        
        # 🆕 期权 Realized P&L 跟踪
        self.total_options_realized_pnl = 0.0  # 期权平仓的累积已实现P&L
        
        # 🆕 记录 RiskManager 启动时间（作为 P&L 计算的起点）
        from datetime import datetime
        self.risk_manager_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🆕 初始化 OKX 客户端
        simulated = (env == "testnet")
        self.options_client = OKXOptionsClient(simulated=simulated)
        # Perp client 不需要单独初始化，使用函数式API
        
        self.logger.info(f"✅ [OKX] RiskManager 初始化完成")
        self.logger.info(f"   启动时间: {self.risk_manager_start_time}")
        self.logger.info(f"   环境: {'模拟盘' if simulated else '实盘'}")
        self.logger.info(f"   最大持仓: {max_positions}")
        self.logger.info(f"   Delta对冲: {'启用' if enable_delta_hedge else '禁用'}")
        if enable_delta_hedge:
            self.logger.info(f"   对冲频率: 每 {hedge_freq} 个监控周期")
            self.logger.info(f"   P&L统计起点: {self.risk_manager_start_time} (仅统计本轮交易)")

        # 初始化波动率跟踪器
        if "BTC" in symbol:
            self.realize_vol_extracter = RealDataEWMAVolTracker(symbol="BTCUSDT", interval=realized_vol_level)
        elif "ETH" in symbol:
            self.realize_vol_extracter = RealDataEWMAVolTracker(symbol="ETHUSDT", interval=realized_vol_level)
        else:
            raise ValueError(f"Invalid symbol: {symbol}")
    
    # ==================== 持仓管理方法 ====================
    
    def add_position(self, position: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity]) -> bool:
        """
        添加新持仓到风险管理器
        
        Args:
            position: Straddle或Calendar Spread持仓
            
        Returns:
            bool: 是否成功添加
        """
        if isinstance(position, StraddleOpportunityOKX):
            if self.can_add_straddle_position():
                position_key = f"straddle_{position.call_option.symbol}_{position.put_option.symbol}"
                if position_key in self.straddle_positions:
                    self.logger.warning(f"⚠️ 持仓已存在: {position_key}")
                    return False 

                self.straddle_positions[position_key] = position
                self.logger.info(f"✅ [OKX] 添加Straddle持仓: {position_key}")
                return True 
            else:
                self.logger.warning(f"⚠️ Straddle持仓已满: {len(self.straddle_positions)}/{self.max_positions}")
                return False
                
        elif isinstance(position, CalendarSpreadOpportunity):
            if self.can_add_calendar_spread_position():
                position_key = f"calendar_{position.short_option.symbol}_{position.long_option.symbol}"
                if position_key in self.calendar_spread_positions:
                    self.logger.warning(f"⚠️ 持仓已存在: {position_key}")
                    return False

                self.calendar_spread_positions[position_key] = position
                self.logger.info(f"✅ [OKX] 添加Calendar Spread持仓: {position_key}")
                return True
            else:
                self.logger.warning(f"⚠️ Calendar持仓已满: {len(self.calendar_spread_positions)}/{self.max_positions}")
                return False
        else:
            raise ValueError(f"Invalid position type: {type(position)}")

    def can_add_straddle_position(self) -> bool:
        """检查是否可以添加新的Straddle持仓"""
        return len(self.straddle_positions) < self.max_positions

    def can_add_calendar_spread_position(self) -> bool:
        """检查是否可以添加新的Calendar Spread持仓"""
        return len(self.calendar_spread_positions) < self.max_positions

    def remove_position(self, position: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity]) -> bool:
        """
        从风险管理器中移除持仓
        
        Args:
            position: 要移除的持仓
            
        Returns:
            bool: 是否成功移除
        """
        if isinstance(position, StraddleOpportunityOKX):
            position_key = f"straddle_{position.call_option.symbol}_{position.put_option.symbol}"
            if position_key in self.straddle_positions:
                del self.straddle_positions[position_key]
                self.logger.info(f"✅ [OKX] 移除Straddle持仓: {position_key}")
                return True
            else:
                self.logger.warning(f"⚠️ 未找到Straddle持仓: {position_key}")
                return False
                
        elif isinstance(position, CalendarSpreadOpportunity):
            position_key = f"calendar_{position.short_option.symbol}_{position.long_option.symbol}"
            if position_key in self.calendar_spread_positions:
                del self.calendar_spread_positions[position_key]
                self.logger.info(f"✅ [OKX] 移除Calendar Spread持仓: {position_key}")
                return True
            else:
                self.logger.warning(f"⚠️ 未找到Calendar Spread持仓: {position_key}")
                return False
        else:
            raise ValueError(f"Invalid position type: {type(position)}")
    
    def get_position_count(self) -> Dict[str, int]:
        """
        获取当前持仓数量
        
        Returns:
            Dict: 包含各类型持仓数量的字典
        """
        return {
            "straddle": len(self.straddle_positions),
            "calendar_spread": len(self.calendar_spread_positions),
            "total": len(self.straddle_positions) + len(self.calendar_spread_positions)
        }
    
    # ==================== 持仓腿检查方法 ====================
    
    def check_position_legs(self, opportunity: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity]) -> Tuple[bool, str]:
        """
        检查策略的两腿是否都存在
        
        Args:
            opportunity: 持仓对象
            
        Returns:
            Tuple[bool, str]: (两腿都存在, 错误信息)
        """
        try:
            if isinstance(opportunity, StraddleOpportunityOKX):
                call_symbol = opportunity.call_option.symbol
                put_symbol = opportunity.put_option.symbol
                
                call_pos = self.options_client.get_position(call_symbol)
                put_pos = self.options_client.get_position(put_symbol)
                
                if not call_pos or float(call_pos.get("pos", 0)) == 0:
                    return False, f"Call腿丢失或已被平仓: {call_symbol}"
                if not put_pos or float(put_pos.get("pos", 0)) == 0:
                    return False, f"Put腿丢失或已被平仓: {put_symbol}"
                    
            elif isinstance(opportunity, CalendarSpreadOpportunity):
                short_symbol = opportunity.short_option.symbol
                long_symbol = opportunity.long_option.symbol
                
                short_pos = self.options_client.get_position(short_symbol)
                long_pos = self.options_client.get_position(long_symbol)
                
                if not short_pos or float(short_pos.get("pos", 0)) == 0:
                    return False, f"Short腿丢失或已被平仓: {short_symbol}"
                if not long_pos or float(long_pos.get("pos", 0)) == 0:
                    return False, f"Long腿丢失或已被平仓: {long_symbol}"
            
            return True, ""
            
        except Exception as e:
            return False, f"检查持仓腿失败: {e}"
    
    # ==================== P&L 查询方法 ====================
    
    def get_opened_opportunities_pnl(self, 
                                     opportunity: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity], 
                                     env: str = "testnet") -> Tuple[Optional[float], Optional[float]]:
        """
        获取已开仓opportunity的精确未实现P&L
        
        Args:
            opportunity: 持仓机会对象
            env: 交易环境 ("testnet" 或 "mainnet")
            
        Returns:
            tuple: (精确未实现P&L, P&L比率)
        """
        try:
            # 确定目标期权合约列表
            if isinstance(opportunity, StraddleOpportunityOKX):
                target_instruments = [
                    opportunity.call_option.symbol,
                    opportunity.put_option.symbol
                ]
                strategy_type = "Straddle"
            elif isinstance(opportunity, CalendarSpreadOpportunity):
                target_instruments = [
                    opportunity.short_option.symbol,
                    opportunity.long_option.symbol
                ]
                strategy_type = "Calendar Spread"
            else:
                self.logger.error(f"❌ 未知的opportunity类型: {type(opportunity)}")
                return None, None
            
            # 获取持仓信息
            pos_1 = self.options_client.get_position(target_instruments[0])
            pos_2 = self.options_client.get_position(target_instruments[1])
            
            if not pos_1 or not pos_2:
                self.logger.warning(f"⚠️ [OKX] 无法获取持仓信息")
                return None, None
            
            # 获取总持仓数量和当前opportunity的合约数量
            # 注意单位转换：
            # - API返回的pos单位是 coins
            # - opportunity.contracts单位是 币本位（如 ETH）
            # - 转换关系（ctMult）：
            #   * ETH: 1 coin = 0.1 ETH
            #   * BTC: 1 coin = 0.01 BTC
            
            # 根据币种确定 CONTRACT_SIZE (ctMult)
            if target_instruments[0].startswith("BTC"):
                CONTRACT_SIZE = 0.01  # BTC
            elif target_instruments[0].startswith("ETH"):
                CONTRACT_SIZE = 0.1   # ETH
            else:
                # 默认使用 ETH 的值，但记录警告
                CONTRACT_SIZE = 0.1
                self.logger.warning(f"⚠️ 未知币种，使用默认 CONTRACT_SIZE = 0.1") 
            
            total_pos_1 = abs(float(pos_1.get("pos", 0)))  # API返回的总持仓（contracts）
            total_pos_2 = abs(float(pos_2.get("pos", 0)))
            opportunity_contracts_crypto = opportunity.contracts  # opportunity存储的合约数（币本位）
            opportunity_contracts_api = opportunity_contracts_crypto / CONTRACT_SIZE  # 转换为API的合约数（张）
            
            # 🔍 调试信息
            self.logger.info(f"🔍 [调试] P&L计算中间变量:")
            self.logger.info(f"   total_pos_1 (API返回): {total_pos_1} 张")
            self.logger.info(f"   total_pos_2 (API返回): {total_pos_2} 张")
            self.logger.info(f"   opportunity_contracts_crypto: {opportunity_contracts_crypto} 币")
            self.logger.info(f"   opportunity_contracts_api: {opportunity_contracts_api} 张")
            
            # 计算份额比例（使用API单位的合约数）
            ratio_1 = opportunity_contracts_api / total_pos_1 if total_pos_1 > 0 else 0
            ratio_2 = opportunity_contracts_api / total_pos_2 if total_pos_2 > 0 else 0
            
            self.logger.info(f"   ratio_1: {ratio_1:.4f} ({ratio_1:.2%})")
            self.logger.info(f"   ratio_2: {ratio_2:.4f} ({ratio_2:.2%})")
            
            # OKX 返回的 upl 是该symbol的总未实现盈亏，需要按份额分配
            total_upl_1 = float(pos_1.get("upl", 0.0))
            total_upl_2 = float(pos_2.get("upl", 0.0))
            
            self.logger.info(f"   total_upl_1 (API返回): {total_upl_1:.8f} ETH")
            self.logger.info(f"   total_upl_2 (API返回): {total_upl_2:.8f} ETH")
            
            # 按份额计算当前opportunity的P&L
            precise_pnl_1 = total_upl_1 * ratio_1
            precise_pnl_2 = total_upl_2 * ratio_2
            precise_pnl = precise_pnl_1 + precise_pnl_2
            
            self.logger.info(f"   precise_pnl_1 = {total_upl_1:.8f} × {ratio_1:.4f} = {precise_pnl_1:.8f}")
            self.logger.info(f"   precise_pnl_2 = {total_upl_2:.8f} × {ratio_2:.4f} = {precise_pnl_2:.8f}")

            # 计算 P&L 比率（基于当前opportunity的成本，使用API单位）
            open_price_1 = float(pos_1.get("avgPx", 0.0))  # 单价（ETH/contract）
            open_price_2 = float(pos_2.get("avgPx", 0.0))
            
            self.logger.info(f"   open_price_1 (Short均价): {open_price_1:.8f} ETH/币")
            self.logger.info(f"   open_price_2 (Long均价): {open_price_2:.8f} ETH/币")
            
            # 计算成本基准
            # 注意：avgPx 的单位是 ETH/币（币本位），不是 ETH/张
            # 所以要用 opportunity_contracts_crypto（币本位）来计算
            if strategy_type == "Calendar Spread":
                # Calendar Spread: 净投入成本 = |Long买入 - Short卖出| × 币本位数量
                net_cost = abs((open_price_2 + open_price_1) * opportunity_contracts_crypto)
                self.logger.info(f"   成本计算 (Calendar): |({open_price_2:.8f} + {open_price_1:.8f})| × {opportunity_contracts_crypto} 币 = {net_cost:.8f}")
            else:
                # Straddle: 收到的权利金总额（或支付的权利金总额）
                net_cost = (open_price_1 + open_price_2) * opportunity_contracts_crypto
                self.logger.info(f"   成本计算 (Straddle): ({open_price_1:.8f} + {open_price_2:.8f}) × {opportunity_contracts_crypto} 币 = {net_cost:.8f}")
            
            pnl_ratio = precise_pnl / net_cost if net_cost > 0 else 0.0
            self.logger.info(f"   P&L比率: {precise_pnl:.8f} / {net_cost:.8f} = {pnl_ratio:+.4f} ({pnl_ratio:+.2%})")

            # 获取Delta信息
            if isinstance(opportunity, StraddleOpportunityOKX):
                delta_1 = opportunity.call_option.net_delta  # Call Delta
                delta_2 = opportunity.put_option.net_delta   # Put Delta
                delta_label_1 = "Call Δ"
                delta_label_2 = "Put Δ"
            elif isinstance(opportunity, CalendarSpreadOpportunity):
                delta_1 = opportunity.short_option.net_delta  # Short Delta
                delta_2 = opportunity.long_option.net_delta   # Long Delta
                delta_label_1 = "Short Δ"
                delta_label_2 = "Long Δ"
            else:
                delta_1 = 0.0
                delta_2 = 0.0
                delta_label_1 = "Δ"
                delta_label_2 = "Δ"
            
            self.logger.info(f"📊 [OKX] {strategy_type} P&L:")
            self.logger.info(f"   {target_instruments[0]}: {precise_pnl_1:+.8f} | {delta_label_1}={delta_1:+.4f} | 总持仓:{total_pos_1}张={total_pos_1*CONTRACT_SIZE}币 | 份额:{ratio_1:.2%} | 均价:{open_price_1:.4f}")
            self.logger.info(f"   {target_instruments[1]}: {precise_pnl_2:+.8f} | {delta_label_2}={delta_2:+.4f} | 总持仓:{total_pos_2}张={total_pos_2*CONTRACT_SIZE}币 | 份额:{ratio_2:.2%} | 均价:{open_price_2:.4f}")
            self.logger.info(f"   Opportunity: {opportunity_contracts_crypto}币 = {opportunity_contracts_api}张")
            self.logger.info(f"   净成本: {net_cost:.8f} ETH")
            self.logger.info(f"   Total P&L: {precise_pnl:+.8f} ({pnl_ratio:+.2%})")
            
            return precise_pnl, pnl_ratio
            
        except Exception as e:
            self.logger.error(f"❌ [OKX] 获取P&L失败: {e}")
            return None, None
    
    def _get_index_price(self, currency: str) -> float:
        """
        获取 OKX 指数价格
        
        Args:
            currency: 币种 ("BTC" 或 "ETH")
            
        Returns:
            float: 指数价格
        """
        try:
            inst_id = f"{currency}-USD"
            url = "https://www.okx.com/api/v5/market/index-tickers"
            params = {"instId": inst_id}
            
            resp = requests.get(url, params=params, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("code") == "0" and data.get("data"):
                return float(data["data"][0].get("idxPx", 0))
            
            return 0.0
        except Exception as e:
            self.logger.error(f"❌ [OKX] 获取指数价格失败 {currency}: {e}")
            return 0.0
    
    # ==================== 平仓方法 ====================
    
    def close_positions(self, 
                        position: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity], 
                        use_async: bool = True, 
                        use_aggressive: bool = False, 
                        env: str = "testnet", 
                        close_reason: str = "Unknown",
                        position_close_log: Optional[str] = None) -> Dict[str, Any]:
        """
        平仓方法
        
        Args:
            position: 持仓对象
            use_async: 是否使用异步协同平仓（仅支持Calendar Spread）
            use_aggressive: 异步平仓时是否使用激进模式（默认False=保守模式）
            env: 交易环境
            close_reason: 平仓原因
            position_close_log: 日志文件路径
            
        Returns:
            dict: 平仓结果
        """
        close_amount = position.contracts
        
        # 🆕 如果使用异步平仓且是Calendar Spread
        if use_async and isinstance(position, CalendarSpreadOpportunity):
            self.logger.info(f"🚀 [OKX] 使用异步协同平仓 Calendar Spread")
            self.logger.info(f"   模式: {'激进' if use_aggressive else '保守'}")
            self.logger.info(f"   原因: {close_reason}")
            
            try:
                from qtrade.optionstrader.master_trader.async_coordinated_order_placer import close_calendar_spread_async
                
                # 调用异步平仓函数
                result = close_calendar_spread_async(
                    opportunity=position,
                    crypto_notional=close_amount,
                    simulated=(env == "testnet"),
                    aggressive=use_aggressive
                )
                
                if result.get("success"):
                    self.logger.info(f"✅ [OKX] 异步平仓成功")
                    self.logger.info(f"   总耗时: {result.get('total_time', 0):.2f}秒")
                    
                    # 🆕 获取并累加realized P&L
                    short_close = result.get("short_close")
                    long_close = result.get("long_close")
                    
                    import time
                    time.sleep(2)  # 等待订单完全处理
                    
                    total_pnl = 0.0
                    currency = position.short_option.symbol.split("-")[0]
                    
                    # 查询Short腿的P&L
                    if short_close and hasattr(short_close, 'order_id'):
                        self.logger.info(f"   Short: {short_close.filled_sz}张 @ {short_close.avg_px:.6f}")
                        
                        try:
                            short_order_details = self.options_client.get_order_details(
                                inst_id=position.short_option.symbol,
                                ord_id=short_close.order_id
                            )
                            
                            if short_order_details:
                                short_pnl = float(short_order_details.get('pnl', 0) or 0)
                                short_fee = float(short_order_details.get('fee', 0) or 0)
                                total_pnl += short_pnl
                                
                                self.logger.info(f"   💰 Short平仓P&L: {short_pnl:+.8f} {currency}")
                                self.logger.info(f"      手续费: {short_fee:+.8f} {currency}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Short P&L失败: {e}")
                    
                    # 查询Long腿的P&L
                    if long_close and hasattr(long_close, 'order_id'):
                        self.logger.info(f"   Long: {long_close.filled_sz}张 @ {long_close.avg_px:.6f}")
                        
                        try:
                            long_order_details = self.options_client.get_order_details(
                                inst_id=position.long_option.symbol,
                                ord_id=long_close.order_id
                            )
                            
                            if long_order_details:
                                long_pnl = float(long_order_details.get('pnl', 0) or 0)
                                long_fee = float(long_order_details.get('fee', 0) or 0)
                                total_pnl += long_pnl
                                
                                self.logger.info(f"   💰 Long平仓P&L: {long_pnl:+.8f} {currency}")
                                self.logger.info(f"      手续费: {long_fee:+.8f} {currency}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Long P&L失败: {e}")
                    
                    # 累加到总realized P&L
                    self.total_options_realized_pnl += total_pnl
                    self.logger.info(f"   📊 本次平仓总P&L: {total_pnl:+.8f} {currency}")
                    self.logger.info(f"   📊 累计已实现P&L: {self.total_options_realized_pnl:+.8f} {currency}")
                    
                    # 记录平仓信息
                    if position_close_log:
                        self._record_position_close(position, close_reason, position_close_log, env)
                    
                    return result
                else:
                    self.logger.error(f"❌ [OKX] 异步平仓失败: {result.get('error')}")
                    # 失败则回退到传统平仓方式
                    self.logger.warning(f"   ⚠️ 回退到传统平仓方式...")
                    
            except Exception as e:
                self.logger.error(f"❌ [OKX] 异步平仓异常: {e}")
                self.logger.warning(f"   ⚠️ 回退到传统平仓方式...")
        
        # 传统平仓方式（或异步平仓失败后的回退） 

        if isinstance(position, StraddleOpportunityOKX):
            # 平仓 Call 和 Put (使用限价单强制成交)
            try:
                # 检查哪些腿还存在
                call_pos = self.options_client.get_position(position.call_option.symbol)
                put_pos = self.options_client.get_position(position.put_option.symbol)
                
                call_exists = call_pos and float(call_pos.get("pos", 0)) != 0
                put_exists = put_pos and float(put_pos.get("pos", 0)) != 0
                
                if not call_exists and not put_exists:
                    self.logger.warning(f"⚠️ [OKX] Straddle两腿都已不存在，无需平仓")
                    return {"success": True, "message": "两腿都已平仓"}
                
                # 获取当前市场价格
                from qtrade.order_api.okx.func_call.options_market_data import get_okx_option_market_data
                
                call_result = None
                put_result = None
                
                # 平仓存在的Call腿
                if call_exists:
                    call_data = get_okx_option_market_data(position.call_option.symbol, simulated=(env == "testnet"))
                    if call_data:
                        self.logger.info(f"📊 [OKX] 平仓Straddle Call腿 - 使用限价单")
                        self.logger.info(f"   Call: ask={call_data['ask']:.6f}")
                        
                        call_result = self.options_client.place_limit_order_crypto_notional(
                            inst_id=position.call_option.symbol,
                            side="buy",
                            crypto_notional=close_amount,
                            px=call_data["ask"],
                            reduce_only=True
                        )
                        
                        # 检查订单是否成功（使用 success 字段）
                        if not call_result.get("success"):
                            raise Exception(f"Call平仓失败: {call_result}")
                        
                        order_id = call_result.get('ordId')
                        self.logger.info(f"   ✅ Call: {position.call_option.symbol} - OrderID: {order_id}")
                        
                        # 🆕 获取平仓P&L
                        import time
                        time.sleep(2)  # 等待订单成交
                        
                        try:
                            order_details = self.options_client.get_order_details(
                                inst_id=position.call_option.symbol,
                                ord_id=order_id
                            )
                            
                            if order_details:
                                pnl = float(order_details.get('pnl', 0) or 0)
                                avg_px = float(order_details.get('avgPx', 0) or 0)
                                filled_sz = int(float(order_details.get('accFillSz', 0) or 0))
                                fee = float(order_details.get('fee', 0) or 0)
                                
                                self.total_options_realized_pnl += pnl
                                
                                currency = position.call_option.symbol.split("-")[0]
                                self.logger.info(f"   💰 Call平仓P&L: {pnl:+.8f} {currency}")
                                self.logger.info(f"      成交: {filled_sz}张 @ {avg_px:.6f}, 手续费: {fee:+.8f}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Call平仓P&L失败: {e}")
                    else:
                        self.logger.warning(f"⚠️ 无法获取Call价格，跳过")
                else:
                    self.logger.info(f"   ⏭️ Call腿已不存在，跳过")
                
                # 平仓存在的Put腿
                if put_exists:
                    put_data = get_okx_option_market_data(position.put_option.symbol, simulated=(env == "testnet"))
                    if put_data:
                        self.logger.info(f"📊 [OKX] 平仓Straddle Put腿 - 使用限价单")
                        self.logger.info(f"   Put: ask={put_data['ask']:.6f}")
                        
                        put_result = self.options_client.place_limit_order_crypto_notional(
                            inst_id=position.put_option.symbol,
                            side="buy",
                            crypto_notional=close_amount,
                            px=put_data["ask"],
                            reduce_only=True
                        )
                        
                        # 检查订单是否成功（使用 success 字段）
                        if not put_result.get("success"):
                            raise Exception(f"Put平仓失败: {put_result}")
                        
                        order_id = put_result.get('ordId')
                        self.logger.info(f"   ✅ Put: {position.put_option.symbol} - OrderID: {order_id}")
                        
                        # 🆕 获取平仓P&L
                        import time
                        time.sleep(2)  # 等待订单成交
                        
                        try:
                            order_details = self.options_client.get_order_details(
                                inst_id=position.put_option.symbol,
                                ord_id=order_id
                            )
                            
                            if order_details:
                                pnl = float(order_details.get('pnl', 0) or 0)
                                avg_px = float(order_details.get('avgPx', 0) or 0)
                                filled_sz = int(float(order_details.get('accFillSz', 0) or 0))
                                fee = float(order_details.get('fee', 0) or 0)
                                
                                self.total_options_realized_pnl += pnl
                                
                                currency = position.put_option.symbol.split("-")[0]
                                self.logger.info(f"   💰 Put平仓P&L: {pnl:+.8f} {currency}")
                                self.logger.info(f"      成交: {filled_sz}张 @ {avg_px:.6f}, 手续费: {fee:+.8f}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Put平仓P&L失败: {e}")
                    else:
                        self.logger.warning(f"⚠️ 无法获取Put价格，跳过")
                else:
                    self.logger.info(f"   ⏭️ Put腿已不存在，跳过")
                
                self.logger.info(f"✅ [OKX] Straddle平仓完成")
                
            except Exception as e:
                self.logger.error(f"❌ [OKX] Straddle平仓失败: {e}")
                return {"success": False, "error": str(e)}

        elif isinstance(position, CalendarSpreadOpportunity):
            # 平仓 Short 和 Long (使用限价单强制成交)
            try:
                # 检查哪些腿还存在
                short_pos = self.options_client.get_position(position.short_option.symbol)
                long_pos = self.options_client.get_position(position.long_option.symbol)
                
                short_exists = short_pos and float(short_pos.get("pos", 0)) != 0
                long_exists = long_pos and float(long_pos.get("pos", 0)) != 0
                
                if not short_exists and not long_exists:
                    self.logger.warning(f"⚠️ [OKX] Calendar Spread两腿都已不存在，无需平仓")
                    return {"success": True, "message": "两腿都已平仓"}
                
                # 获取当前市场价格
                from qtrade.order_api.okx.func_call.options_market_data import get_okx_option_market_data
                
                short_result = None
                long_result = None
                
                # 平仓存在的Short腿
                if short_exists:
                    short_data = get_okx_option_market_data(position.short_option.symbol, simulated=(env == "testnet"))
                    if short_data:
                        self.logger.info(f"📊 [OKX] 平仓Calendar Short腿 - 使用限价单")
                        self.logger.info(f"   Short: ask={short_data['ask']:.6f}")
                        
                        short_result = self.options_client.place_limit_order_crypto_notional(
                            inst_id=position.short_option.symbol,
                            side="buy",  # 买回Short
                            crypto_notional=close_amount,
                            px=short_data["ask"],
                            reduce_only=True
                        )
                        
                        # 检查订单是否成功（使用 success 字段）
                        if not short_result.get("success"):
                            raise Exception(f"Short平仓失败: {short_result}")
                        
                        order_id = short_result.get('ordId')
                        self.logger.info(f"   ✅ Short: {position.short_option.symbol} - OrderID: {order_id}")
                        
                        # 🆕 获取平仓P&L
                        import time
                        time.sleep(2)
                        
                        try:
                            order_details = self.options_client.get_order_details(
                                inst_id=position.short_option.symbol,
                                ord_id=order_id
                            )
                            
                            if order_details:
                                pnl = float(order_details.get('pnl', 0) or 0)
                                avg_px = float(order_details.get('avgPx', 0) or 0)
                                filled_sz = int(float(order_details.get('accFillSz', 0) or 0))
                                fee = float(order_details.get('fee', 0) or 0)
                                
                                self.total_options_realized_pnl += pnl
                                
                                currency = position.short_option.symbol.split("-")[0]
                                self.logger.info(f"   💰 Short平仓P&L: {pnl:+.8f} {currency}")
                                self.logger.info(f"      成交: {filled_sz}张 @ {avg_px:.6f}, 手续费: {fee:+.8f}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Short平仓P&L失败: {e}")
                    else:
                        self.logger.warning(f"⚠️ 无法获取Short价格，跳过")
                else:
                    self.logger.info(f"   ⏭️ Short腿已不存在，跳过")
                
                # 平仓存在的Long腿
                if long_exists:
                    long_data = get_okx_option_market_data(position.long_option.symbol, simulated=(env == "testnet"))
                    if long_data:
                        self.logger.info(f"📊 [OKX] 平仓Calendar Long腿 - 使用限价单")
                        self.logger.info(f"   Long: bid={long_data['bid']:.6f}")
                        
                        long_result = self.options_client.place_limit_order_crypto_notional(
                            inst_id=position.long_option.symbol,
                            side="sell",  # 卖出Long
                            crypto_notional=close_amount,
                            px=long_data["bid"],
                            reduce_only=True
                        )
                        
                        # 检查订单是否成功（使用 success 字段）
                        if not long_result.get("success"):
                            raise Exception(f"Long平仓失败: {long_result}")
                        
                        order_id = long_result.get('ordId')
                        self.logger.info(f"   ✅ Long: {position.long_option.symbol} - OrderID: {order_id}")
                        
                        # 🆕 获取平仓P&L
                        import time
                        time.sleep(2)
                        
                        try:
                            order_details = self.options_client.get_order_details(
                                inst_id=position.long_option.symbol,
                                ord_id=order_id
                            )
                            
                            if order_details:
                                pnl = float(order_details.get('pnl', 0) or 0)
                                avg_px = float(order_details.get('avgPx', 0) or 0)
                                filled_sz = int(float(order_details.get('accFillSz', 0) or 0))
                                fee = float(order_details.get('fee', 0) or 0)
                                
                                self.total_options_realized_pnl += pnl
                                
                                currency = position.long_option.symbol.split("-")[0]
                                self.logger.info(f"   💰 Long平仓P&L: {pnl:+.8f} {currency}")
                                self.logger.info(f"      成交: {filled_sz}张 @ {avg_px:.6f}, 手续费: {fee:+.8f}")
                        except Exception as e:
                            self.logger.warning(f"   ⚠️ 获取Long平仓P&L失败: {e}")
                    else:
                        self.logger.warning(f"⚠️ 无法获取Long价格，跳过")
                else:
                    self.logger.info(f"   ⏭️ Long腿已不存在，跳过")
                
                self.logger.info(f"✅ [OKX] Calendar Spread平仓完成")
                
            except Exception as e:
                self.logger.error(f"❌ [OKX] Calendar Spread平仓失败: {e}")
                return {"success": False, "error": str(e)}
        
        # TODO: 记录平仓信息到日志文件
        if position_close_log:
            self._record_position_close(position, close_reason, position_close_log, env)
        
        return {"success": True, "message": "Position closed successfully"}
    
    def _record_position_close(self, 
                              position: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity], 
                              close_reason: str, 
                              position_close_log: str, 
                              env: str):
        """记录平仓信息到日志文件"""
        try:
            from datetime import datetime
            
            current_time = datetime.now()
            timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取当前P&L信息
            try:
                current_pnl, current_pnl_ratio = self.get_opened_opportunities_pnl(position, env)
            except:
                current_pnl, current_pnl_ratio = 0.0, 0.0
            
            # 构建记录信息
            record_info = f"""
            === OKX POSITION CLOSE RECORD ===
            Time: {timestamp}
            Close Reason: {close_reason}
            Position Type: {"Straddle" if isinstance(position, StraddleOpportunityOKX) else "Calendar Spread"}
            Contracts: {position.contracts}
            P&L: {current_pnl:+.6f} ({current_pnl_ratio:+.2%})
            Environment: {env}
            {'='*50}

            """
            
            # 写入日志文件
            with open(position_close_log, 'a', encoding='utf-8') as f:
                f.write(record_info)
            
            self.logger.info(f"📝 [OKX] 平仓信息已记录到: {position_close_log}")
            
        except Exception as e:
            self.logger.error(f"❌ [OKX] 记录平仓信息失败: {e}")

    # ==================== Delta对冲方法 ====================
    
    def hedge_action(self, 
                     newly_hedge_size: float, 
                     instrument: str = "BTC-USD-SWAP",  # OKX 永续合约格式
                     order_type: str = "market", 
                     price: Optional[float] = None, 
                     env: str = "testnet") -> Optional[Dict[str, Any]]:
        """
        Delta对冲方法（使用OKX永续合约）
        
        Args:
            newly_hedge_size: 新增对冲数量（币本位，如 0.1 BTC）
            instrument: 对冲合约 (OKX: "BTC-USD-SWAP" / "ETH-USD-SWAP")
            order_type: 订单类型 ("market" 或 "limit")
            price: 限价单价格
            env: 环境
            
        Returns:
            dict: 对冲结果
        """
        if not self.enable_delta_hedge:
            self.logger.info("⚠️ [OKX] Delta对冲未启用")
            return None
    
        if abs(newly_hedge_size) < self.delta_hedge_threshold:
            self.logger.info(f"⚠️ [OKX] 对冲数量太小 ({newly_hedge_size:.4f})，跳过")
            return None
        
        # 确定对冲方向
        hedge_side = "buy" if newly_hedge_size > 0 else "sell"
        hedge_amount = abs(newly_hedge_size)
        direction_desc = "做多" if newly_hedge_size > 0 else "做空"
        
        self.logger.info(f"📊 [OKX] 执行Delta对冲:")
        self.logger.info(f"   对冲Delta: {newly_hedge_size:.4f}")
        self.logger.info(f"   对冲方向: {direction_desc} {instrument}")
        self.logger.info(f"   对冲数量: {hedge_amount:.4f} (币本位)")
        self.logger.info(f"   订单类型: {order_type.upper()}")
        
        try:
            # 使用新的通用API进行对冲
            from qtrade.order_api.okx.func_call.perp.perp_order import place_inverse_perp_order_crypto_notional
            
            # 确定是否使用模拟盘
            simulated = (env == "testnet")
            
            # 使用 isolated 模式进行对冲
            self.logger.info(f"   保证金模式: ISOLATED (逐仓)")
            
            if order_type == "market":
                order_id, result = place_inverse_perp_order_crypto_notional(
                    instId=instrument,
                    side=hedge_side,
                    crypto_notional=hedge_amount,
                    ordType="market",
                    tdMode="isolated",  # 🔒 使用逐仓模式
                    simulated=simulated
                )
            elif order_type == "limit" and price:
                self.logger.info(f"   限价价格: ${price:,.2f}")
                order_id, result = place_inverse_perp_order_crypto_notional(
                    instId=instrument,
                    side=hedge_side,
                    crypto_notional=hedge_amount,
                    ordType="limit",
                    px=price,
                    tdMode="isolated",  # 🔒 使用逐仓模式
                    simulated=simulated
                )
            else:
                raise ValueError(f"无效的订单类型: {order_type}")
            
            # place_inverse_perp_order_crypto_notional 返回 (order_id, result) 元组
            if order_id:
                self.logger.info(f"✅ [OKX] 对冲成功 - OrderID: {order_id}")
                self.logger.info(f"   保证金模式: ISOLATED")
                return result
            else:
                raise Exception(f"OKX API error: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ [OKX] 对冲失败: {e}")
            raise
    
    # ==================== 持仓更新与监控方法 ====================
    
    def update_positions(self, realized_vol: float, env: str = "testnet", position_close_log: Optional[str] = None) -> float:
        """
        更新所有持仓的Greeks并计算组合的Net Delta
        
        Args:
            realized_vol: 实现波动率
            env: 交易环境 ("testnet" 或 "mainnet")
            position_close_log: 平仓日志文件路径
            
        Returns:
            float: 组合的总Net Delta
        """
        
        total_net_delta = 0.0
        updated_positions = 0
        
        self.logger.info(f"🔄 [OKX] 开始更新所有持仓的Greeks...")
        self.logger.info(f"   Straddle持仓: {len(self.straddle_positions)}")
        self.logger.info(f"   Calendar Spread持仓: {len(self.calendar_spread_positions)}")
        
        # 更新所有Straddle持仓
        if len(self.straddle_positions) > 0:
            self.logger.info(f"\n📊 [OKX] 更新Straddle持仓...")
            
            straddle_items = self.straddle_positions.items()
            positions_to_close = []
            
            for position_key, straddle_position in straddle_items:
                self.logger.info(f"   🔄 更新Straddle: {position_key}")
                
                try:
                    # 🔍 检查两腿是否都存在
                    legs_ok, legs_error = self.check_position_legs(straddle_position)
                    if not legs_ok:
                        self.logger.error(f"🚨 [OKX] Straddle持仓腿缺失: {position_key}")
                        self.logger.error(f"   错误: {legs_error}")
                        self.logger.warning(f"   ⚠️ 将标记为紧急平仓（另一腿将被平掉）")
                        positions_to_close.append(("straddle", position_key, straddle_position, f"持仓腿缺失 - {legs_error}"))
                        continue
                    
                    # 更新Net Delta（完整模式）
                    update_straddle_opportunity_okx(
                        opportunity=straddle_position,
                        realized_vol=realized_vol,
                        net_delta_only=False
                    )

                    # ⚠️ 重要：需要将单位Delta乘以持仓数量（contracts）
                    # straddle_position.call_option.net_delta 和 put_option.net_delta 是单位Delta（每合约）
                    # straddle_position.contracts 是币本位持仓数量（如 0.1 ETH）
                    contracts = straddle_position.contracts
                    call_unit_delta = straddle_position.call_option.net_delta
                    put_unit_delta = straddle_position.put_option.net_delta
                    
                    # Combined Net Delta = (Call Unit Delta + Put Unit Delta) × Contracts
                    updated_net_delta = (call_unit_delta + put_unit_delta) * contracts
                    
                    self.logger.info(f"   📊 Delta详情: Call Δ={call_unit_delta:.4f}, Put Δ={put_unit_delta:.4f}, Contracts={contracts:.4f}")
                    self.logger.info(f"   📊 Combined Net Delta: {updated_net_delta:.6f}")

                    # 检查是否超过风险阈值
                    if abs(updated_net_delta) > self.delta_risk_threshold:
                        self.logger.warning(f"⚠️ [OKX] Straddle持仓 {position_key} 超过风险阈值: {updated_net_delta:.4f}")
                        positions_to_close.append(("straddle", position_key, straddle_position, "Delta风险过高"))
                        continue

                    # 检查平仓条件
                    close_condition, close_reason = self.check_close_condition(straddle_position, env)
                    if close_condition:
                        self.logger.warning(f"⚠️ [OKX] Straddle持仓 {position_key} 需要平仓: {close_reason}")
                        positions_to_close.append(("straddle", position_key, straddle_position, close_reason))
                        continue
                    
                    total_net_delta += updated_net_delta
                    updated_positions += 1
                    
                    self.logger.info(f"   ✅ Net Delta: {updated_net_delta:.4f}")
                    
                except Exception as e:
                    self.logger.error(f"❌ [OKX] 更新Straddle持仓失败 {position_key}: {e}")
            
            # 关闭需要平仓的持仓
            for pos_type, pos_key, position, reason in positions_to_close:
                try:
                    # 🎯 根据平仓原因智能选择平仓模式
                    # Delta风险过高 或 止损 → 使用传统平仓（快速）
                    # 其他情况（止盈、IV反转等） → 使用异步保守平仓（节省成本）
                    use_async = True
                    use_aggressive = False
                    
                    if "Delta风险过高" in reason or "止损" in reason or "持仓腿缺失" in reason:
                        use_async = False  # 紧急情况使用传统方式
                        self.logger.info(f"⚠️ [OKX] 紧急平仓原因: {reason} → 使用传统平仓方式")
                    elif isinstance(position, CalendarSpreadOpportunity):
                        self.logger.info(f"💰 [OKX] 正常平仓原因: {reason} → 使用异步保守平仓")
                    else:
                        use_async = False  # Straddle暂不支持异步平仓
                    
                    self.close_positions(
                        position=position, 
                        use_async=use_async,
                        use_aggressive=use_aggressive,
                        env=env, 
                        close_reason=reason, 
                        position_close_log=position_close_log
                    )
                    del self.straddle_positions[pos_key]
                    self.logger.info(f"✅ [OKX] 已关闭并移除Straddle持仓: {pos_key}")
                except Exception as e:
                    self.logger.error(f"❌ [OKX] 关闭Straddle持仓失败 {pos_key}: {e}")
        
        # 更新所有Calendar Spread持仓
        if len(self.calendar_spread_positions) > 0:
            self.logger.info(f"\n📊 [OKX] 更新Calendar Spread持仓...")
            
            calendar_items = self.calendar_spread_positions.items()
            positions_to_close = []
            
            for position_key, calendar_position in calendar_items:
                self.logger.info(f"   🔄 更新Calendar Spread: {position_key}")
                
                try:
                    # 🔍 检查两腿是否都存在
                    legs_ok, legs_error = self.check_position_legs(calendar_position)
                    if not legs_ok:
                        self.logger.error(f"🚨 [OKX] Calendar Spread持仓腿缺失: {position_key}")
                        self.logger.error(f"   错误: {legs_error}")
                        self.logger.warning(f"   ⚠️ 将标记为紧急平仓（另一腿将被平掉）")
                        positions_to_close.append(("calendar", position_key, calendar_position, f"持仓腿缺失 - {legs_error}"))
                        continue
                    
                    # 更新Net Delta（完整模式）
                    update_calendar_spread_opportunity(
                        opportunity=calendar_position,
                        realized_vol=realized_vol,
                        net_delta_only=False,
                        env=env
                    )

                    # ⚠️ 重要：需要将单位Delta乘以持仓数量（contracts）
                    # calendar_position.short_option.net_delta 和 long_option.net_delta 是单位Delta（每合约）
                    # calendar_position.contracts 是币本位持仓数量（如 0.1 ETH）
                    contracts = calendar_position.contracts
                    short_unit_delta = calendar_position.short_option.net_delta
                    long_unit_delta = calendar_position.long_option.net_delta
                    
                    # Calendar Spread Net Delta = (Long Unit Delta - Short Unit Delta) × Contracts
                    # 因为我们买入Long（+Delta），卖出Short（-Delta）
                    updated_net_delta = (long_unit_delta - short_unit_delta) * contracts
                    
                    self.logger.info(f"   📊 Delta详情: Short Δ={short_unit_delta:.4f}, Long Δ={long_unit_delta:.4f}, Contracts={contracts:.4f}")
                    self.logger.info(f"   📊 Combined Net Delta: {updated_net_delta:.6f}")

                    # 检查是否超过风险阈值
                    if abs(updated_net_delta) > self.delta_risk_threshold:
                        self.logger.warning(f"⚠️ [OKX] Calendar持仓 {position_key} 超过风险阈值: {updated_net_delta:.4f}")
                        positions_to_close.append(("calendar", position_key, calendar_position, "Delta风险过高"))
                        continue

                    # 检查平仓条件
                    close_condition, close_reason = self.check_close_condition(calendar_position, env)
                    if close_condition:
                        self.logger.warning(f"⚠️ [OKX] Calendar Spread持仓 {position_key} 需要平仓: {close_reason}")
                        positions_to_close.append(("calendar", position_key, calendar_position, close_reason))
                        continue
                    
                    total_net_delta += updated_net_delta
                    updated_positions += 1
                    
                    self.logger.info(f"   ✅ Net Delta: {updated_net_delta:.4f}")
                    
                except Exception as e:
                    self.logger.error(f"❌ [OKX] 更新Calendar持仓失败 {position_key}: {e}")
            
            # 关闭需要平仓的持仓
            for pos_type, pos_key, position, reason in positions_to_close:
                try:
                    # 🎯 根据平仓原因智能选择平仓模式
                    # Delta风险过高 或 止损 → 使用传统平仓（快速）
                    # 其他情况（止盈、IV反转等） → 使用异步保守平仓（节省成本）
                    use_async = True
                    use_aggressive = False
                    
                    if "Delta风险过高" in reason or "止损" in reason or "持仓腿缺失" in reason:
                        use_async = False  # 紧急情况使用传统方式
                        self.logger.info(f"⚠️ [OKX] 紧急平仓原因: {reason} → 使用传统平仓方式")
                    elif isinstance(position, CalendarSpreadOpportunity):
                        self.logger.info(f"💰 [OKX] 正常平仓原因: {reason} → 使用异步保守平仓")
                    else:
                        use_async = False  # Straddle暂不支持异步平仓
                    
                    self.close_positions(
                        position=position, 
                        use_async=use_async,
                        use_aggressive=use_aggressive,
                        env=env, 
                        close_reason=reason, 
                        position_close_log=position_close_log
                    )
                    del self.calendar_spread_positions[pos_key]
                    self.logger.info(f"✅ [OKX] 已关闭并移除Calendar持仓: {pos_key}")
                except Exception as e:
                    self.logger.error(f"❌ [OKX] 关闭Calendar持仓失败 {pos_key}: {e}")
        
        self.logger.info(f"\n📊 [OKX] Greeks更新完成:")
        self.logger.info(f"   更新持仓数: {updated_positions}")
        self.logger.info(f"   总Net Delta: {total_net_delta:.4f}")
        self.logger.info(f"   风险状态: {'⚠️ 需要对冲' if abs(total_net_delta) > self.delta_hedge_threshold else '✅ 风险可控'}")
        
        return total_net_delta
    
    def check_close_condition(self, 
                             position: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity], 
                             env: str = "testnet") -> Tuple[bool, str]:
        """
        检查平仓条件
        
        Args:
            position: 持仓机会对象
            env: 环境 ("testnet" 或 "mainnet")
            
        Returns:
            tuple: (should_close: bool, reason: str)
        """
        try:
            # 获取当前P&L
            current_pnl, current_pnl_ratio = self.get_opened_opportunities_pnl(position, env)
            
            if current_pnl is None:
                return False, "无法获取P&L信息"

            # 根据策略类型调用对应的平仓检查方法
            if isinstance(position, StraddleOpportunityOKX):
                return self._check_straddle_close_condition(position, current_pnl, current_pnl_ratio, env)
            elif isinstance(position, CalendarSpreadOpportunity):
                return self._check_calendar_close_condition(position, current_pnl, current_pnl_ratio, env)
            else:
                self.logger.error(f"❌ [OKX] 未知的position类型: {type(position)}")
                return False, "未知策略类型"
                
        except Exception as e:
            self.logger.error(f"❌ [OKX] 检查平仓条件失败: {e}")
            return False, f"检查失败: {e}"
    
    def monitor_positions(self, check_duration: str = "5min"):
        """
        持续监控持仓（自动化交易的核心循环）
        
        Args:
            check_duration: 检查间隔 ("1min", "5min", "10min", "15min", "30min", "1hour")
        """
        # 转换检查间隔为秒数
        check_duration_seconds = self._transform_check_duration(check_duration)
        
        self.logger.info(f"🚀 [OKX] 开始监控持仓 (间隔: {check_duration})")
        
        while True:
            try:
                # 获取当前实现波动率
                current_realize_vol = self.realize_vol_extracter.predict()['realized_vol_annualized']
                
                # 更新所有持仓
                total_net_delta = self.update_positions(current_realize_vol, self.env, None)

                # 📊 获取永续合约持仓信息
                from qtrade.order_api.okx.func_call.perp.perp_order import get_current_positions
                instrument = "BTC-USD-SWAP" if "BTC" in self.realize_vol_extracter.symbol else "ETH-USD-SWAP"
                perp_positions = get_current_positions(instType="SWAP", instId=instrument, silent=True)
                
                # 计算永续合约P&L和持仓
                perp_delta = 0.0
                perp_unrealized_pnl = 0.0  # 未实现P&L
                if perp_positions:
                    for pos in perp_positions:
                        pos_size = float(pos.get("pos", 0))
                        if pos_size != 0:
                            upl = float(pos.get("upl", 0))
                            perp_unrealized_pnl += upl
                            # 对于反向合约，pos就是合约数量（张），需要转换为币本位Delta
                            # 反向合约: 1张 ≈ ctVal USD / 当前价格 币
                            ct_val = float(pos.get("ctVal", 0))
                            mark_px = float(pos.get("markPx", 0))
                            if mark_px > 0:
                                # Delta = pos (张) × ctVal (USD/张) / markPx (USD/币) = 币数量
                                perp_delta += (pos_size * ct_val / mark_px)
                
                # 📈 更新永续合约已实现P&L（从交易历史中获取）
                if self.enable_delta_hedge:
                    try:
                        from qtrade.optionstrader.trading_engine.okx_engine.perp_pnl_tracker import get_perp_realized_pnl
                        
                        # 确定查询起始时间
                        if self.last_perp_fill_time is None:
                            # 首次查询：从 RiskManager 启动时间开始
                            # 这样可以确保只统计本轮交易的 P&L，不会包含上一轮的历史数据
                            start_time = self.risk_manager_start_time
                        else:
                            # 后续查询：使用上次的结束时间（函数内部会自动往前推5分钟）
                            start_time = str(self.last_perp_fill_time)
                        
                        # 调用增量更新函数
                        self.total_perp_realized_pnl, self.last_perp_fill_time = get_perp_realized_pnl(
                            instrument=instrument,
                            start_time=start_time,
                            perp_pnl_dict=self.perp_pnl_dict,
                            previous_realized_pnl=self.total_perp_realized_pnl,
                            silent=True  # 在监控循环中静默模式
                        )
                        self.logger.debug(f"✅ [OKX] 永续合约已实现P&L已更新: {self.total_perp_realized_pnl:+.8f} {self.realize_vol_extracter.symbol[:3]}")
                    except Exception as e:
                        self.logger.warning(f"⚠️ [OKX] 更新永续合约已实现P&L失败: {e}")
                
                # 永续合约总P&L = 未实现P&L + 已实现P&L
                perp_total_pnl = perp_unrealized_pnl + self.total_perp_realized_pnl
                
                # 计算期权总P&L
                options_pnl = 0.0
                for pos_key, position in list(self.straddle_positions.items()) + list(self.calendar_spread_positions.items()):
                    try:
                        pnl, _ = self.get_opened_opportunities_pnl(position, self.env)
                        if pnl is not None:
                            options_pnl += pnl
                    except:
                        pass
                
                # 总P&L = 期权未实现P&L + 期权已实现P&L + 永续合约总P&L
                total_pnl = options_pnl + self.total_options_realized_pnl + perp_total_pnl
                
                # 打印综合信息
                currency = self.realize_vol_extracter.symbol[:3]
                print(f"\n{'='*70}")
                print(f"📊 持仓状态汇总")
                print(f"{'='*70}")
                print(f"🎯 期权持仓:")
                print(f"   Combined Delta: {total_net_delta:+.6f} {currency}")
                print(f"   未实现P&L: {options_pnl:+.8f} {currency}")
                print(f"   已实现P&L: {self.total_options_realized_pnl:+.8f} {currency}")
                print(f"   期权Total: {(options_pnl + self.total_options_realized_pnl):+.8f} {currency}")
                print(f"\n🔒 永续合约对冲:")
                print(f"   已对冲Delta: {self.current_hedged_delta:+.6f} {currency}")
                print(f"   实际持仓Delta: {perp_delta:+.6f} {currency}")
                print(f"   未实现P&L: {perp_unrealized_pnl:+.8f} {currency}")
                print(f"   已实现P&L: {self.total_perp_realized_pnl:+.8f} {currency} (累计{len(self.perp_pnl_dict)}笔成交)")
                print(f"   永续合约Total: {perp_total_pnl:+.8f} {currency}")
                print(f"\n💰 总P&L (期权+永续): {total_pnl:+.8f} {currency}")
                print(f"{'='*70}\n")

                # 🔒 安全检查：如果没有期权持仓且启用了对冲，清理所有永续合约仓位
                total_option_positions = len(self.straddle_positions) + len(self.calendar_spread_positions)
                if total_option_positions == 0:
                    if self.enable_delta_hedge:
                        self.logger.info("📊 [MainThread] 当前无期权持仓，检查永续合约仓位...")
                        self._cleanup_orphan_perp_positions()
                        
                        # 🆕 检查是否还有永续合约仓位
                        perp_positions_after_cleanup = get_current_positions(instType="SWAP", instId=instrument, silent=True)
                        has_perp = False
                        if perp_positions_after_cleanup:
                            for pos in perp_positions_after_cleanup:
                                if float(pos.get("pos", 0)) != 0:
                                    has_perp = True
                                    break
                        
                        # 如果无任何仓位，退出监控循环
                        if not has_perp:
                            self.logger.info("✅ [MainThread] 所有仓位已平仓，退出监控循环")
                            self.logger.info(f"📊 最终统计:")
                            self.logger.info(f"   期权已实现P&L: {self.total_options_realized_pnl:+.8f} {currency}")
                            self.logger.info(f"   永续已实现P&L: {self.total_perp_realized_pnl:+.8f} {currency}")
                            self.logger.info(f"   总已实现P&L: {(self.total_options_realized_pnl + self.total_perp_realized_pnl):+.8f} {currency}")
                            break  # 退出while True循环
                    else:
                        self.logger.debug("⏭️ [MainThread] 当前无期权持仓且未启用对冲，退出监控循环")
                        self.logger.info(f"📊 最终统计:")
                        self.logger.info(f"   期权已实现P&L: {self.total_options_realized_pnl:+.8f} {currency}")
                        break  # 退出while True循环
                else:
                    self.logger.info(f"📊 [MainThread] 持仓状态: Calendar={len(self.calendar_spread_positions)}, Straddle={len(self.straddle_positions)}")
                    
                    # Delta对冲逻辑（仅在启用对冲且有期权持仓时执行）
                    if self.enable_delta_hedge:
                        # 增加计数器
                        self.hedge_counter += 1
                        
                        # 检查是否到达对冲频率
                        if self.hedge_counter >= self.hedge_freq:
                            # 重置计数器
                            self.hedge_counter = 0
                            
                            hedge_delta_diff = -total_net_delta - self.current_hedged_delta

                            if abs(hedge_delta_diff) > self.delta_hedge_threshold:
                                self.logger.info(f"📊 [OKX] 执行Delta对冲: {hedge_delta_diff:.4f}")
                                # 确定合约类型
                                instrument = "BTC-USD-SWAP" if "BTC" in self.realize_vol_extracter.symbol else "ETH-USD-SWAP"
                                self.hedge_action(hedge_delta_diff, instrument, "market", None, self.env)
                                self.current_hedged_delta = -total_net_delta
                            else:
                                self.logger.debug(f"✅ [OKX] Delta在安全范围内 (Δ差异={hedge_delta_diff:.4f} < 阈值={self.delta_hedge_threshold})")
                        else:
                            self.logger.debug(f"⏭️ [OKX] 对冲计数器: {self.hedge_counter}/{self.hedge_freq} (下次对冲周期还需 {self.hedge_freq - self.hedge_counter} 个监控周期)")
                    else:
                        self.logger.debug(f"⏭️ [OKX] Delta对冲已禁用 (当前Net Delta={total_net_delta:.4f})")

                time.sleep(check_duration_seconds)
                
            except Exception as e:
                self.logger.error(f"❌ [OKX] 监控循环出错: {e}")
                time.sleep(check_duration_seconds)
    
    def _cleanup_orphan_perp_positions(self):
        """
        清理孤立的永续合约仓位（当没有期权持仓时）
        
        如果系统中没有任何期权持仓（Calendar Spread或Straddle），
        但存在永续合约对冲仓位，将自动平掉所有永续合约仓位。
        """
        try:
            from qtrade.order_api.okx.func_call.perp.perp_order import get_current_positions
            
            # 确定要检查的合约
            instrument = "BTC-USD-SWAP" if "BTC" in self.realize_vol_extracter.symbol else "ETH-USD-SWAP"
            
            # 获取当前永续合约仓位
            positions = get_current_positions(instType="SWAP", instId=instrument)
            
            if not positions:
                self.logger.info(f"✅ [OKX] 无永续合约仓位，无需清理")
                # 重置对冲delta记录
                if self.current_hedged_delta != 0:
                    self.logger.info(f"🔄 [OKX] 重置对冲Delta记录: {self.current_hedged_delta:.4f} → 0")
                    self.current_hedged_delta = 0
                return
            
            # 找到实际持仓
            active_positions = [p for p in positions if float(p.get("pos", 0)) != 0]
            
            if not active_positions:
                self.logger.info(f"✅ [OKX] {instrument} 无持仓，无需清理")
                if self.current_hedged_delta != 0:
                    self.logger.info(f"🔄 [OKX] 重置对冲Delta记录: {self.current_hedged_delta:.4f} → 0")
                    self.current_hedged_delta = 0
                return
            
            # 有持仓需要平掉
            self.logger.warning(f"⚠️ [OKX] 检测到孤立永续合约仓位！")
            for pos in active_positions:
                pos_size = float(pos.get("pos", 0))
                pos_side = pos.get("posSide", "net")
                avg_px = float(pos.get("avgPx", 0))
                upl = float(pos.get("upl", 0))
                
                self.logger.warning(f"   合约: {instrument}")
                self.logger.warning(f"   仓位: {pos_size} 张 ({pos_side})")
                self.logger.warning(f"   均价: ${avg_px:,.2f}")
                self.logger.warning(f"   未实现盈亏: {upl:.6f}")
                
                # 平仓
                self.logger.info(f"🔄 [OKX] 开始平仓永续合约...")
                self._close_perp_position(instrument, pos)
            
            # 重置对冲delta记录
            self.logger.info(f"✅ [OKX] 永续合约仓位已清理完毕")
            self.current_hedged_delta = 0
                
        except Exception as e:
            self.logger.error(f"❌ [OKX] 清理永续合约仓位失败: {e}")
    
    def _close_perp_position(self, instrument: str, position: Dict[str, Any]):
        """
        平掉单个永续合约仓位
        
        Args:
            instrument: 合约ID (e.g., "ETH-USD-SWAP")
            position: 仓位信息字典
        """
        try:
            from qtrade.order_api.okx.func_call.perp.perp_order import place_inverse_perp_order_crypto_notional
            
            pos_size = float(position.get("pos", 0))
            pos_side_raw = position.get("posSide", "net")
            
            if pos_size == 0:
                self.logger.info(f"⏭️ [OKX] {instrument} 仓位为0，跳过")
                return
            
            # 确定平仓方向和数量
            # pos > 0 表示多头持仓，需要卖出平仓
            # pos < 0 表示空头持仓，需要买入平仓
            close_side = "sell" if pos_size > 0 else "buy"
            
            # 获取合约信息计算crypto notional
            from qtrade.order_api.okx.func_call.utils import get_instrument_details, get_current_btc_price
            
            ct_val = float(get_instrument_details(instrument)["ctVal"])
            current_price = get_current_btc_price(instrument)
            
            # 计算需要平仓的crypto notional
            abs_contracts = abs(int(pos_size))
            usd_notional = abs_contracts * ct_val
            crypto_notional = usd_notional / current_price
            
            self.logger.info(f"📊 [OKX] 平仓参数:")
            self.logger.info(f"   合约数量: {abs_contracts} 张")
            self.logger.info(f"   USD名义值: ${usd_notional:.2f}")
            self.logger.info(f"   Crypto数量: {crypto_notional:.6f}")
            self.logger.info(f"   平仓方向: {close_side}")
            
            # 确定是否使用模拟盘
            simulated = (self.env == "testnet")
            
            # 执行平仓（使用 isolated 模式，与开仓保持一致）
            order_id, result = place_inverse_perp_order_crypto_notional(
                instId=instrument,
                side=close_side,
                crypto_notional=crypto_notional,
                ordType="market",
                tdMode="isolated",
                simulated=simulated
            )
            
            if order_id:
                self.logger.info(f"✅ [OKX] 永续合约平仓成功 - OrderID: {order_id}")
            else:
                self.logger.error(f"❌ [OKX] 永续合约平仓失败: {result}")
                
        except Exception as e:
            self.logger.error(f"❌ [OKX] 平仓永续合约时出错: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
    
    def _transform_check_duration(self, check_duration: str) -> int:
        """
        转换时间间隔字符串为秒数
        
        Args:
            check_duration: 时间字符串 ("5min", "10min", etc.)
            
        Returns:
            int: 秒数
        """
        duration_map = {
            "1min": 60,
            "5min": 300,
            "10min": 600,
            "15min": 900,
            "30min": 1800,
            "1hour": 3600
        }
        
        if check_duration not in duration_map:
            raise ValueError(f"无效的检查间隔: {check_duration}. 支持: {list(duration_map.keys())}")
        
        return duration_map[check_duration]
    
    # ==================== 平仓条件检查方法 ====================
    
    def _check_straddle_close_condition(self, 
                                       position: StraddleOpportunityOKX, 
                                       current_pnl: float, 
                                       current_pnl_ratio: float, 
                                       env: str) -> Tuple[bool, str]:
        """
        Straddle策略平仓条件检查
        
        检查项：
        1. 止损/止盈
        2. IV反转（IV下降，对卖方有利则平仓）
        3. 价格变化风险（现货价格偏离过大）
        4. 时间衰减保护（临近到期）
        
        Args:
            position: Straddle持仓对象
            current_pnl: 当前P&L
            current_pnl_ratio: P&L比率
            env: 环境
            
        Returns:
            tuple: (should_close, reason)
        """
        # 1. 止损/止盈检查
        if current_pnl_ratio <= self.stop_loss_ratio:
            return True, f"止损平仓 (P&L: {current_pnl_ratio:.1%})"
        
        if current_pnl_ratio >= self.profit_target_ratio:
            return True, f"止盈平仓 (P&L: {current_pnl_ratio:.1%})"
        
        # 2. IV反转检查（检测IV是否大幅下降）
        try:
            # 获取开仓时的IV
            call_entry_iv = getattr(position, 'call_option_entry_iv', None)
            put_entry_iv = getattr(position, 'put_option_entry_iv', None)
            
            if call_entry_iv and put_entry_iv:
                call_current_iv = position.call_option.iv
                put_current_iv = position.put_option.iv
                
                call_iv_change = (call_current_iv - call_entry_iv) / call_entry_iv
                put_iv_change = (put_current_iv - put_entry_iv) / put_entry_iv
                
                self.logger.info(f"📊 [OKX] IV变化: Call {call_iv_change:+.1%}, Put {put_iv_change:+.1%}")
                
                # 如果IV大幅上升（不利于卖方），考虑平仓
                if call_iv_change > 0.3 or put_iv_change > 0.3:
                    return True, f"Straddle IV剧烈上升风险平仓 (Call: {call_iv_change:+.1%}, Put: {put_iv_change:+.1%})"
        except Exception as e:
            self.logger.warning(f"⚠️ [OKX] IV反转检查失败: {e}")
        
        # 3. 价格变化检查
        try:
            entry_spot_price = getattr(position, 'entry_spot_price', 0)
            
            if entry_spot_price > 0:
                currency = position.call_option.symbol.split('-')[0]
                current_spot_price = self._get_index_price(currency)
                
                if current_spot_price > 0:
                    price_change_ratio = abs(current_spot_price - entry_spot_price) / entry_spot_price
                    
                    self.logger.info(f"📊 [OKX] 价格变化: {price_change_ratio:+.1%}")
                    
                    if price_change_ratio > self.price_change_risk_ratio:
                        return True, f"价格变化过大风险平仓 (变化: {price_change_ratio:.1%})"
        except Exception as e:
            self.logger.warning(f"⚠️ [OKX] 价格变化检查失败: {e}")
        
        # 4. 时间衰减保护（接近到期）
        try:
            days_to_expiry = min(
                position.call_option.days_to_expiry,
                position.put_option.days_to_expiry
            )
            
            if days_to_expiry <= 1:
                return True, f"时间衰减保护平仓 (剩余: {days_to_expiry} 天)"
        except Exception as e:
            self.logger.warning(f"⚠️ [OKX] 时间衰减检查失败: {e}")
        
        return False, ""
    
    def _check_calendar_close_condition(self, 
                                       position: CalendarSpreadOpportunity, 
                                       current_pnl: float, 
                                       current_pnl_ratio: float, 
                                       env: str) -> Tuple[bool, str]:
        """
        Calendar Spread策略平仓条件检查
        
        检查项：
        1. 止损/止盈
        2. IV价差反转（短期IV低于长期IV）
        3. 时间衰减（短期期权接近到期）
        
        Args:
            position: Calendar Spread持仓对象
            current_pnl: 当前P&L
            current_pnl_ratio: P&L比率
            env: 环境
            
        Returns:
            tuple: (should_close, reason)
        """
        
        # 1. 止损/止盈检查
        if current_pnl_ratio <= self.stop_loss_ratio:
            return True, f"止损平仓 (P&L: {current_pnl_ratio:.1%})"
        
        if current_pnl_ratio >= self.profit_target_ratio:
            return True, f"止盈平仓 (P&L: {current_pnl_ratio:.1%})"
        
        # 2. IV价差反转检查
        try:
            short_iv = position.short_option.iv
            long_iv = position.long_option.iv
            current_iv_spread = short_iv - long_iv
            
            # Calendar Spread的核心逻辑：
            # - 正常情况：Short IV ≈ Long IV 或略高（价差通常 0-5%）
            # - 只要不显著反转（Short IV < Long IV - 1%），策略就是有效的
            # - 只有当IV价差显著为负时才需要平仓
            
            if current_iv_spread < -0.01:  # IV价差显著为负（< -1%）
                return True, f"IV价差显著反转平仓 (Short IV: {short_iv:.2%}, Long IV: {long_iv:.2%}, 价差: {current_iv_spread:.2%})"
        
        except Exception as e:
            self.logger.warning(f"⚠️ [OKX] IV价差检查失败: {e}")
        
        # 3. 时间衰减检查（短期期权接近到期）
        try:
            short_days_to_expiry = position.short_option.days_to_expiry
            
            if short_days_to_expiry <= 2:
                return True, f"短期期权接近到期平仓 (剩余: {short_days_to_expiry} 天)"
        
        except Exception as e:
            self.logger.warning(f"⚠️ [OKX] 时间衰减检查失败: {e}")
        
        return False, ""


def create_okx_risk_manager(
    symbol: str = "BTCUSDT",
    max_positions: int = 1,
    enable_delta_hedge: bool = False,
    env: str = "testnet",
    **kwargs
) -> OKXRiskManager:
    """
    创建 OKX RiskManager 的便捷函数
    
    Args:
        symbol: 交易对
        max_positions: 最大持仓数
        enable_delta_hedge: 是否启用Delta对冲
        env: 交易环境
        **kwargs: 其他参数
        
    Returns:
        OKXRiskManager: 风险管理器实例
    """
    return OKXRiskManager(
        symbol=symbol,
        max_positions=max_positions,
        enable_delta_hedge=enable_delta_hedge,
        env=env,
        **kwargs
    )

