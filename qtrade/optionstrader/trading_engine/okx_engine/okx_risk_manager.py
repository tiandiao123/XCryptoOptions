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
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder_deribit import update_straddle_opportunity
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

        # 🆕 初始化 OKX 客户端
        simulated = (env == "testnet")
        self.options_client = OKXOptionsClient(simulated=simulated)
        # Perp client 不需要单独初始化，使用函数式API
        
        self.logger.info(f"✅ [OKX] RiskManager 初始化完成")
        self.logger.info(f"   环境: {'模拟盘' if simulated else '实盘'}")
        self.logger.info(f"   最大持仓: {max_positions}")
        self.logger.info(f"   Delta对冲: {'启用' if enable_delta_hedge else '禁用'}")

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
            
            # OKX 直接返回 upl（未实现盈亏）
            precise_pnl_1 = float(pos_1.get("upl", 0.0))
            precise_pnl_2 = float(pos_2.get("upl", 0.0))
            precise_pnl = precise_pnl_1 + precise_pnl_2

            # 计算 P&L 比率
            contract_size = opportunity.contracts
            open_price_1 = float(pos_1.get("avgPx", 0.0))
            open_price_2 = float(pos_2.get("avgPx", 0.0))
            total_options_cost = open_price_1 * contract_size + open_price_2 * contract_size
            pnl_ratio = precise_pnl / total_options_cost if total_options_cost > 0 else 0.0

            self.logger.info(f"📊 [OKX] {strategy_type} P&L:")
            self.logger.info(f"   {target_instruments[0]}: {precise_pnl_1:.8f}")
            self.logger.info(f"   {target_instruments[1]}: {precise_pnl_2:.8f}")
            self.logger.info(f"   Total: {precise_pnl:.8f} ({pnl_ratio:+.2%})")
            
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
                        env: str = "testnet", 
                        close_reason: str = "Unknown",
                        position_close_log: Optional[str] = None) -> Dict[str, Any]:
        """
        平仓方法
        
        Args:
            position: 持仓对象
            env: 交易环境
            close_reason: 平仓原因
            position_close_log: 日志文件路径
            
        Returns:
            dict: 平仓结果
        """
        close_amount = position.contracts 

        if isinstance(position, StraddleOpportunityOKX):
            # 平仓 Call 和 Put
            try:
                call_result = self.options_client.place_market_order_crypto_notional(
                    inst_id=position.call_option.symbol,
                    side="buy",
                    crypto_notional=close_amount,
                    reduce_only=True
                )
                
                put_result = self.options_client.place_market_order_crypto_notional(
                    inst_id=position.put_option.symbol,
                    side="buy",
                    crypto_notional=close_amount,
                    reduce_only=True
                )
                
                call_success = (call_result.get("sCode") == "0")
                put_success = (put_result.get("sCode") == "0")
                
                if not call_success:
                    raise Exception(f"Call平仓失败: {call_result}")
                if not put_success:
                    raise Exception(f"Put平仓失败: {put_result}")
                
                self.logger.info(f"✅ [OKX] Straddle平仓成功")
                self.logger.info(f"   Call: {position.call_option.symbol} - OrderID: {call_result.get('ordId')}")
                self.logger.info(f"   Put: {position.put_option.symbol} - OrderID: {put_result.get('ordId')}")
                
            except Exception as e:
                self.logger.error(f"❌ [OKX] Straddle平仓失败: {e}")
                return {"success": False, "error": str(e)}

        elif isinstance(position, CalendarSpreadOpportunity):
            # 平仓 Short 和 Long
            try:
                short_result = self.options_client.place_market_order_crypto_notional(
                    inst_id=position.short_option.symbol,
                    side="buy",  # 买回Short
                    crypto_notional=close_amount,
                    reduce_only=True
                )
                
                long_result = self.options_client.place_market_order_crypto_notional(
                    inst_id=position.long_option.symbol,
                    side="sell",  # 卖出Long
                    crypto_notional=close_amount,
                    reduce_only=True
                )
                
                short_success = (short_result.get("sCode") == "0")
                long_success = (long_result.get("sCode") == "0")
                
                if not short_success:
                    raise Exception(f"Short平仓失败: {short_result}")
                if not long_success:
                    raise Exception(f"Long平仓失败: {long_result}")
                
                self.logger.info(f"✅ [OKX] Calendar Spread平仓成功")
                self.logger.info(f"   Short: {position.short_option.symbol} - OrderID: {short_result.get('ordId')}")
                self.logger.info(f"   Long: {position.long_option.symbol} - OrderID: {long_result.get('ordId')}")
                
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
            # 使用函数式API进行对冲
            from qtrade.order_api.okx.func_call.perp.perp_order import place_inverse_perp_order_with_btc_notional
            
            if order_type == "market":
                result = place_inverse_perp_order_with_btc_notional(
                    inst_id=instrument,
                    side=hedge_side,
                    btc_amount=hedge_amount,
                    order_type="market"
                )
            elif order_type == "limit" and price:
                self.logger.info(f"   限价价格: ${price:,.2f}")
                result = place_inverse_perp_order_with_btc_notional(
                    inst_id=instrument,
                    side=hedge_side,
                    btc_amount=hedge_amount,
                    order_type="limit",
                    price=price
                )
            else:
                raise ValueError(f"无效的订单类型: {order_type}")
            
            if result.get("code") == "0" and result.get("data"):
                order_data = result["data"][0]
                if order_data.get("sCode") == "0":
                    self.logger.info(f"✅ [OKX] 对冲成功 - OrderID: {order_data.get('ordId')}")
                    return result
                else:
                    raise Exception(f"OKX API error: {order_data.get('sMsg')}")
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
                    # 更新Net Delta（完整模式）
                    update_straddle_opportunity(
                        opportunity=straddle_position,
                        realized_vol=realized_vol,
                        net_delta_only=False,
                        env=env
                    )

                    updated_net_delta = straddle_position.call_option.net_delta + straddle_position.put_option.net_delta

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
                    self.close_positions(position, env, reason, position_close_log)
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
                    # 更新Net Delta（完整模式）
                    update_calendar_spread_opportunity(
                        opportunity=calendar_position,
                        realized_vol=realized_vol,
                        net_delta_only=False,
                        env=env
                    )

                    # Calendar Spread Net Delta = Long Delta - Short Delta
                    updated_net_delta = calendar_position.long_option.net_delta - calendar_position.short_option.net_delta

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
                    self.close_positions(position, env, reason, position_close_log)
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
            check_duration: 检查间隔 ("5min", "10min", "15min", "30min")
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

                # Delta对冲逻辑
                hedge_delta_diff = -total_net_delta - self.current_hedged_delta

                if abs(hedge_delta_diff) > self.delta_hedge_threshold:
                    self.logger.info(f"📊 [OKX] 执行Delta对冲: {hedge_delta_diff:.4f}")
                    # 确定合约类型
                    instrument = "BTC-USD-SWAP" if "BTC" in self.realize_vol_extracter.symbol else "ETH-USD-SWAP"
                    self.hedge_action(hedge_delta_diff, instrument, "market", None, self.env)
                    self.current_hedged_delta = -total_net_delta

                time.sleep(check_duration_seconds)
                
            except Exception as e:
                self.logger.error(f"❌ [OKX] 监控循环出错: {e}")
                time.sleep(check_duration_seconds)
    
    def _transform_check_duration(self, check_duration: str) -> int:
        """
        转换时间间隔字符串为秒数
        
        Args:
            check_duration: 时间字符串 ("5min", "10min", etc.)
            
        Returns:
            int: 秒数
        """
        duration_map = {
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
            
            # Calendar Spread依赖短期IV > 长期IV
            # 如果IV价差消失或反转，应该平仓
            if current_iv_spread <= 0:
                return True, f"IV价差反转平仓 (Short IV: {short_iv:.2%}, Long IV: {long_iv:.2%})"
            
            # 如果IV价差缩小到很小，也考虑平仓
            if current_iv_spread < 0.02:  # IV价差小于2%
                return True, f"IV价差过小平仓 (价差: {current_iv_spread:.2%})"
        
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

