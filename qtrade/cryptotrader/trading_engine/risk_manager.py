

from collections import deque
from typing import Any, Dict, Union
import logging

from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import CalendarSpreadOpportunity
# 导入更新
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import update_straddle_opportunity
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import update_calendar_spread_opportunity
from qtrade.cryptotrader.trading_engine.containers.thread_safe_map import ThreadSafeMap
from qtrade.order_api.deribit_order_placer.futures_order import place_limit_order_btc_notional, place_market_order_btc_notional
from qtrade.order_api.deribit_order_placer.options_order import place_options_market_order_btc_notional
from qtrade.order_api.deribit_order_placer.positions_info import get_total_pnl_for_instruments, get_multiple_options_position_info


class RiskManager:
    def __init__(self, 
                 max_positions: int = 1, 
                 enable_delta_hedge: bool = False, 
                 delta_hedge_threshold: float = 0.05,
                 delta_risk_threshold: float = 0.5): 

        self.max_positions = max_positions
        self.enable_delta_hedge = enable_delta_hedge
        self.delta_risk_threshold = delta_risk_threshold
        self.delta_hedge_threshold = delta_hedge_threshold
        self.current_hedged_delta = 0.0 

        # 初始化日志记录器
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

        self.straddle_positions = ThreadSafeMap()
        self.calendar_spread_positions = ThreadSafeMap()
    

    def add_position(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity]):
        """
        添加新持仓到风险管理器
        
        Args:
            position: Straddle或Calendar Spread持仓
        """
        if isinstance(position, StraddleOpportunity):
            if self.can_add_straddle_position():
                # 使用symbol作为key，确保唯一性
                position_key = f"straddle_{position.call_option.symbol}_{position.put_option.symbol}"
                if position_key in self.straddle_positions:
                    print(f"have already got this opened position: {position_key}, ignore at this time")
                    return False 

                self.straddle_positions.put(position_key, position)
                print(f"✅ 添加Straddle持仓: {position_key}")
                return True 
            else:
                print(f"Straddle持仓已满: {self.straddle_positions.size()}/{self.max_positions}")
                
        elif isinstance(position, CalendarSpreadOpportunity):
            if self.can_add_calendar_spread_position():
                # 使用symbol作为key，确保唯一性
                position_key = f"calendar_{position.short_option.symbol}_{position.long_option.symbol}"
                if position_key in self.calendar_spread_positions:
                    print(f"have already got this opened position: {position_key}, ignore at this time")
                    return False 

                self.calendar_spread_positions.put(position_key, position)
                print(f"✅ 添加Calendar Spread持仓: {position_key}")
                return True 
            else:
                print(f"Calendar Spread持仓已满: {self.calendar_spread_positions.size()}/{self.max_positions}")
        
        else:
            print(f"Invalid position type: {type(position)}")
        

        return False 
        
        
    def can_add_straddle_position(self):
        return self.straddle_positions.size() < self.max_positions
    
    def can_add_calendar_spread_position(self):
        return self.calendar_spread_positions.size() < self.max_positions
    
    def remove_position(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity]) -> bool:
        """
        从风险管理器中移除持仓
        
        Args:
            position: 要移除的持仓
            
        Returns:
            bool: 是否成功移除
        """
        if isinstance(position, StraddleOpportunity):
            position_key = f"straddle_{position.call_option.symbol}_{position.put_option.symbol}"
            if self.straddle_positions.contains_key(position_key):
                self.straddle_positions.remove(position_key)
                print(f"✅ 移除Straddle持仓: {position_key}")
                return True
            else:
                print(f"⚠️ 未找到Straddle持仓: {position_key}")
                return False
                
        elif isinstance(position, CalendarSpreadOpportunity):
            position_key = f"calendar_{position.short_option.symbol}_{position.long_option.symbol}"
            if self.calendar_spread_positions.contains_key(position_key):
                self.calendar_spread_positions.remove(position_key)
                print(f"✅ 移除Calendar Spread持仓: {position_key}")
                return True
            else:
                print(f"⚠️ 未找到Calendar Spread持仓: {position_key}")
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
            "straddle": self.straddle_positions.size(),
            "calendar_spread": self.calendar_spread_positions.size(),
            "total": self.straddle_positions.size() + self.calendar_spread_positions.size()
        }
    
    def update_positions_geeks(self, realized_vol: float, env: str = "testnet"):
        """
        更新所有持仓的Greeks并计算组合的Net Delta
        
        Args:
            realized_vol: 实现波动率
            env: 交易环境 ("testnet" 或 "mainnet")
            
        Returns:
            float: 组合的总Net Delta
        """
        
        total_net_delta = 0.0
        updated_positions = 0
        
        print(f"🔄 开始更新所有持仓的Greeks...")
        print(f"   Straddle持仓: {self.straddle_positions.size()}")
        print(f"   Calendar Spread持仓: {self.calendar_spread_positions.size()}")
        
        # 更新所有Straddle持仓
        if self.straddle_positions.size() > 0:
            print(f"\n📊 更新Straddle持仓...")
            
            # 获取所有Straddle持仓的键值对
            straddle_items = self.straddle_positions.get_all_items()
            positions_to_close = []  # 需要关闭的持仓
            
            for position_key, straddle_position in straddle_items:
                print(f"   🔄 更新Straddle: {position_key}")
                
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
                        print(f"⚠️ Straddle持仓 {position_key} 超过风险阈值: {updated_net_delta:.4f}")
                        positions_to_close.append(("straddle", position_key, straddle_position))
                        continue
                    
                    total_net_delta += updated_net_delta
                    updated_positions += 1
                    
                    print(f"   ✅ Net Delta: {updated_net_delta:.4f}")
                    
                except Exception as e:
                    print(f"❌ 更新Straddle持仓失败 {position_key}: {e}")
            
            # 关闭超过风险阈值的持仓
            for pos_type, pos_key, position in positions_to_close:
                try:
                    self.close_positions(position, env)
                    self.straddle_positions.remove(pos_key)
                    print(f"✅ 已关闭并移除Straddle持仓: {pos_key}")
                except Exception as e:
                    print(f"❌ 关闭Straddle持仓失败 {pos_key}: {e}")
        
        # 更新所有Calendar Spread持仓
        if self.calendar_spread_positions.size() > 0:
            print(f"\n📊 更新Calendar Spread持仓...")
            
            # 获取所有Calendar持仓的键值对
            calendar_items = self.calendar_spread_positions.get_all_items()
            positions_to_close = []  # 需要关闭的持仓
            
            for position_key, calendar_position in calendar_items:
                print(f"   🔄 更新Calendar Spread: {position_key}")
                
                try:
                    # 更新Net Delta（完整模式）
                    update_calendar_spread_opportunity(
                        opportunity=calendar_position,
                        realized_vol=realized_vol,
                        net_delta_only=False,
                        env=env
                    )

                    # Calendar Spread Net Delta = Long Delta - Short Delta (修正后的计算)
                    updated_net_delta = calendar_position.long_option.net_delta - calendar_position.short_option.net_delta

                    # 检查是否超过风险阈值
                    if abs(updated_net_delta) > self.delta_risk_threshold:
                        print(f"⚠️ Calendar持仓 {position_key} 超过风险阈值: {updated_net_delta:.4f}")
                        positions_to_close.append(("calendar", position_key, calendar_position))
                        continue
                    
                    total_net_delta += updated_net_delta
                    updated_positions += 1
                    
                    print(f"   ✅ Net Delta: {updated_net_delta:.4f}")
                    
                except Exception as e:
                    print(f"❌ 更新Calendar持仓失败 {position_key}: {e}")
            
            # 关闭超过风险阈值的持仓
            for pos_type, pos_key, position in positions_to_close:
                try:
                    self.close_positions(position, env)
                    self.calendar_spread_positions.remove(pos_key)
                    print(f"✅ 已关闭并移除Calendar持仓: {pos_key}")
                except Exception as e:
                    print(f"❌ 关闭Calendar持仓失败 {pos_key}: {e}")
        
        print(f"\n📊 Greeks更新完成:")
        print(f"   更新持仓数: {updated_positions}")
        print(f"   总Net Delta: {total_net_delta:.4f}")
        print(f"   风险状态: {'⚠️ 需要对冲' if abs(total_net_delta) > self.delta_hedge_threshold else '✅ 风险可控'}")
        
        return total_net_delta
            
    def close_positions(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity], 
                    env: str = "testnet") -> Dict[str, Any]:
        
        close_amount = position.contracts 

        if isinstance(position, StraddleOpportunity):
            call_result = place_options_market_order_btc_notional(
                instrument=position.call_option.symbol,
                side = "buy",
                contracts=close_amount,
                reduce_only=True, 
                env = env, 
            )

            put_result = place_options_market_order_btc_notional(
                instrument=position.put_option.symbol,
                side = "buy",
                contracts=close_amount,
                reduce_only=True, 
                env = env, 
            )

            assert call_result.get("success") is True, f"Error: Failed to close position: {position.call_option.symbol}"
            assert put_result.get("success") is True, f"Error: Failed to close position: {position.put_option.symbol}"

        elif isinstance(position, CalendarSpreadOpportunity):
            short_result = place_options_market_order_btc_notional(
                instrument=position.short_option.symbol,
                side = "buy",
                contracts=close_amount,
                reduce_only=True, 
                env = env, 
            )

            assert short_result.get("success") is True, f"Error: Failed to close position : {position.short_option.symbol}"
 
            long_result = place_options_market_order_btc_notional(
                    instrument=position.long_option.symbol,
                    side="sell",  # 卖出之前买入的长期期权
                    contracts=close_amount,
                    reduce_only=True,  # 只减仓
                    env=env
                )
            
            assert long_result.get("success") is True, f"Error: Failed to close position: {position.long_option.symbol}"


    def hedge_action(self, 
                     newly_hedge_size: float, 
                     instrument: str = "BTC-PERPETUAL", 
                     order_type: str = "market", 
                     price: float = None, 
                     env: str = "testnet"):
        """
        Args:
            newly_hedge_size: 新增对冲数量
            instrutment: 对冲合约
            order_type: 订单类型 (limit or market)
            env: 环境
        """
        if not self.enable_delta_hedge:
            print("Delta对冲未启用，跳过对冲操作")
            return
    
        if abs(newly_hedge_size) < self.delta_hedge_threshold:  # 最小对冲阈值
            print(f"对冲数量太小 ({newly_hedge_size:.4f})，跳过对冲")
            return
        
        # 确定对冲方向和数量
        if newly_hedge_size > 0:
            hedge_side = "buy"   # 做多BTC/ETH
            hedge_amount = abs(newly_hedge_size)
            direction_desc = "做多"
        else:
            hedge_side = "sell"  # 做空BTC/ETH
            hedge_amount = abs(newly_hedge_size)
            direction_desc = "做空"
        
        print(f"执行Delta对冲:")
        print(f"  对冲Delta: {newly_hedge_size:.4f}")
        print(f"  对冲方向: {direction_desc} {instrument}")
        print(f"  对冲数量: {hedge_amount:.4f} BTC")
        print(f"  订单类型: {order_type.upper()}")
        
        if order_type == "limit" and price:
            print(f"  限价价格: ${price:,.2f}")
        
        if order_type == "market":
            hedge_result = place_market_order_btc_notional(
                instrument=instrument,
                side=hedge_side,
                btc_amount=hedge_amount,
                reduce_only=False,
                env=env
            )

            assert hedge_result.get("success") is True, f"Error: Failed to hedge: {instrument}"

        elif order_type == "limit" and price:
            # need to check whether it has been eaten out by the market
            # probably using another thread to check the order status
            hedge_result = place_limit_order_btc_notional(
                instrument=instrument,
                side=hedge_side,
                btc_amount=hedge_amount,
                price=price,
                post_only=False,
                reduce_only=False,
                env=env
            )
        else:
            raise ValueError(f"Invalid order type: {order_type}")
        
        return hedge_result
    
    def get_opened_opportunities_pnl(self, opportunity: Union[StraddleOpportunity, CalendarSpreadOpportunity], env: str = "testnet") -> float:
        """
        获取已开仓opportunity的精确未实现P&L - 基于账户汇总API
        
        Args:
            opportunity: 持仓机会对象
            env: 环境 ("testnet" 或 "mainnet")
            
        Returns:
            float: 精确未实现P&L (BTC)，获取失败返回0.0
        """
        try:
            # 🆕 使用新的精确P&L API
            from qtrade.order_api.deribit_order_placer.positions_info import get_precise_total_pnl_for_instruments
            
            # 确定目标期权合约列表
            if isinstance(opportunity, StraddleOpportunity):
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
                return 0.0
            
            # 获取精确P&L信息
            pnl_result = get_precise_total_pnl_for_instruments(target_instruments, env)
            precise_pnl = pnl_result["total_precise_pnl"]
            
            self.logger.info(f"📊 {strategy_type} 精确P&L: {precise_pnl:.8f} BTC")
            self.logger.info(f"   数据来源: {pnl_result['data_source']}")
            self.logger.info(f"   精度级别: {pnl_result['precision_level']}")
            self.logger.info(f"   找到持仓: {pnl_result['found_count']}/{pnl_result['total_instruments']}")
            
            return precise_pnl
            
        except Exception as e:
            self.logger.error(f"❌ 获取精确P&L失败: {e}")
            return 0.0

    def check_close_condition(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity], 
                            env: str = "testnet") -> tuple:
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
            current_pnl = self.get_opened_opportunities_pnl(position, env)
            
            if current_pnl == 0.0:
                return False, "无法获取P&L信息"
            
            # 计算P&L百分比（基于合约数量）
            if hasattr(position, 'contracts') and position.contracts > 0:
                pnl_pct = current_pnl / position.contracts
            else:
                pnl_pct = current_pnl  # 如果没有合约数量信息，直接使用绝对值
            
            # 获取持仓详细信息用于更精确的判断
            if isinstance(position, StraddleOpportunity):
                target_instruments = [position.call_option.symbol, position.put_option.symbol]
                strategy_type = "Straddle"
                
                # Straddle平仓条件
                if pnl_pct < -0.3:  # -30% 止损
                    return True, f"Straddle止损 (P&L: {pnl_pct*100:.1f}%, {current_pnl:.6f} BTC)"
                elif pnl_pct > 0.5:  # +50% 止盈
                    return True, f"Straddle止盈 (P&L: {pnl_pct*100:.1f}%, {current_pnl:.6f} BTC)"
                
                # TODO: 添加IV反转检查
                # 可以调用 update_straddle_opportunity 获取最新IV进行判断
                
            elif isinstance(position, CalendarSpreadOpportunity):
                target_instruments = [position.short_option.symbol, position.long_option.symbol]
                strategy_type = "Calendar Spread"
                
                # Calendar Spread平仓条件
                if pnl_pct < -0.3:  # -30% 止损
                    return True, f"Calendar止损 (P&L: {pnl_pct*100:.1f}%, {current_pnl:.6f} BTC)"
                elif pnl_pct > 0.5:  # +50% 止盈
                    return True, f"Calendar止盈 (P&L: {pnl_pct*100:.1f}%, {current_pnl:.6f} BTC)"
                
                # TODO: 添加IV价差反转检查
                # 可以调用 update_calendar_spread_opportunity 获取最新IV价差进行判断
            
            else:
                return False, f"未知策略类型: {type(position)}"
            
            return False, f"{strategy_type}继续持有 (P&L: {pnl_pct*100:.1f}%, {current_pnl:.6f} BTC)"
            
        except Exception as e:
            print(f"❌ 检查平仓条件失败: {e}")
            return False, f"检查失败: {str(e)}"
        
    
    def monitor_positions(self):
        pass 