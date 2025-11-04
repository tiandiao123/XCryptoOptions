

from collections import deque
import time
from typing import Any, Dict, Union, Tuple
import logging

from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.ewma_vol_tracker import RealDataEWMAVolTracker
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import CalendarSpreadOpportunity
# 导入更新
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import update_calendar_spread_opportunity
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder_deribit import StraddleOpportunity, update_straddle_opportunity
from qtrade.optionstrader.trading_engine.containers.thread_safe_map import ThreadSafeMap
from qtrade.order_api.deribit.futures_order import place_limit_order_btc_notional, place_market_order_btc_notional
from qtrade.order_api.deribit.options_order import place_options_market_order_btc_notional
from qtrade.order_api.deribit.options_orderbook import get_index_price
from qtrade.order_api.deribit.options_positions_info import get_instrument_open_price, get_instrument_pnl

class RiskManager:
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
        Args:
            max_positions: 最大持仓数量
            enable_delta_hedge: 是否启用Delta对冲
            delta_hedge_threshold: Delta对冲阈值
            delta_risk_threshold: Delta风险阈值
            stop_loss_ratio: 止损百分比
            profit_target_ratio: 止盈百分比
            price_change_risk_ratio: 价格变化风险阈值
            realized_vol_level: 实现波动率级别
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

        self.straddle_positions = ThreadSafeMap()
        self.calendar_spread_positions = ThreadSafeMap()


        # create realize_vol extracter 
        if "BTC" in symbol:
            self.realize_vol_extracter = RealDataEWMAVolTracker(symbol="BTCUSDT", interval=realized_vol_level)
        elif "ETH" in symbol:
            self.realize_vol_extracter = RealDataEWMAVolTracker(symbol="ETHUSDT", interval=realized_vol_level)
        else:
            raise ValueError(f"Invalid symbol: {symbol}")
    

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
            if position_key in self.straddle_positions:
                del self.straddle_positions[position_key]
                print(f"✅ 移除Straddle持仓: {position_key}")
                return True
            else:
                print(f"⚠️ 未找到Straddle持仓: {position_key}")
                return False
                
        elif isinstance(position, CalendarSpreadOpportunity):
            position_key = f"calendar_{position.short_option.symbol}_{position.long_option.symbol}"
            if position_key in self.calendar_spread_positions:
                del self.calendar_spread_positions[position_key]
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
    
    def update_positions(self, realized_vol: float, env: str = "testnet", position_close_log: str = None):
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
        print(f"   Straddle持仓: {len(self.straddle_positions)}")
        print(f"   Calendar Spread持仓: {len(self.calendar_spread_positions)}")
        
        # 更新所有Straddle持仓
        if len(self.straddle_positions) > 0:
            print(f"\n📊 更新Straddle持仓...")
            
            # 获取所有Straddle持仓的键值对
            straddle_items = self.straddle_positions.items()
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

                    close_condition, close_reason = self.check_close_condition(straddle_position, env)
                    if close_condition:
                        print(f"⚠️ Straddle持仓 {position_key} 需要平仓: {close_reason}")
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
                    self.close_positions(position, env, close_reason, position_close_log)
                    del self.straddle_positions[pos_key]
                    print(f"✅ 已关闭并移除Straddle持仓: {pos_key}")
                except Exception as e:
                    print(f"❌ 关闭Straddle持仓失败 {pos_key}: {e}")
        
        # 更新所有Calendar Spread持仓
        if len(self.calendar_spread_positions) > 0:
            print(f"\n📊 更新Calendar Spread持仓...")
            
            # 获取所有Calendar持仓的键值对
            calendar_items = self.calendar_spread_positions.items()
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

                    close_condition, close_reason = self.check_close_condition(calendar_position, env)
                    if close_condition:
                        print(f"⚠️ Calendar Spread持仓 {position_key} 需要平仓: {close_reason}")
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
                    self.close_positions(position, env, close_reason, position_close_log)
                    del self.calendar_spread_positions[pos_key]
                    print(f"✅ 已关闭并移除Calendar持仓: {pos_key}")
                except Exception as e:
                    print(f"❌ 关闭Calendar持仓失败 {pos_key}: {e}")
        
        print(f"\n📊 Greeks更新完成:")
        print(f"   更新持仓数: {updated_positions}")
        print(f"   总Net Delta: {total_net_delta:.4f}")
        print(f"   风险状态: {'⚠️ 需要对冲' if abs(total_net_delta) > self.delta_hedge_threshold else '✅ 风险可控'}")
        
        return total_net_delta
            
    def close_positions(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity], 
                        env: str = "testnet", 
                        close_reason: str = "Unknown",
                        position_close_log: str = None) -> Dict[str, Any]:
        
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
        
        # 🆕 记录平仓信息
        self._record_position_close(position, close_reason, position_close_log, env)
        
        return {"success": True, "message": "Position closed successfully"}
    
    def _record_position_close(self, 
                              position: Union[StraddleOpportunity, CalendarSpreadOpportunity], 
                              close_reason: str, 
                              position_close_log: str, 
                              env: str):
        """记录平仓信息到日志文件"""
        try:
            from datetime import datetime
            
            # 如果没有提供日志文件路径，跳过记录
            if not position_close_log:
                return
            
            current_time = datetime.now()
            timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取当前P&L信息
            try:
                current_pnl, current_pnl_ratio = self.get_opened_opportunities_pnl(position, env)
            except:
                current_pnl, current_pnl_ratio = 0.0, 0.0
            
            # 构建记录信息
            if isinstance(position, StraddleOpportunity):
                position_type = "Straddle"
                position_id = f"{position.call_option.symbol}_{position.put_option.symbol}"
                
                record_info = f"""
                === POSITION CLOSE RECORD ===
                Time: {timestamp}
                Position Type: {position_type}
                Position ID: {position_id}
                Strategy: {position.strategy_type}
                Close Reason: {close_reason}
                Contracts: {position.contracts}

                Options Info:
                Call Option: {position.call_option.symbol}
                    - Strike: ${position.call_option.strike:,.0f}
                    - Days to Expiry: {position.call_option.days_to_expiry}
                    - Entry IV: {getattr(position, 'call_option_entry_iv', 'N/A')}
                    - Current IV: {position.call_option.iv:.4f}
                    - Delta: {position.call_option.delta:+.4f}
                    
                Put Option: {position.put_option.symbol}
                    - Strike: ${position.put_option.strike:,.0f}
                    - Days to Expiry: {position.put_option.days_to_expiry}
                    - Entry IV: {getattr(position, 'put_option_entry_iv', 'N/A')}
                    - Current IV: {position.put_option.iv:.4f}
                    - Delta: {position.put_option.delta:+.4f}

                P&L Information:
                Unrealized P&L: {current_pnl:+.6f} BTC
                P&L Ratio: {current_pnl_ratio:+.2%}
                
                Entry Information:
                Entry Spot Price: ${getattr(position, 'entry_spot_price', 'N/A')}
                Average Entry IV: {(getattr(position, 'call_option_entry_iv', 0) + getattr(position, 'put_option_entry_iv', 0))/2:.4f}
                Total Premium: {position.total_premium:.6f} BTC

                Environment: {env}
                {'='*50}

                """
            
            elif isinstance(position, CalendarSpreadOpportunity):
                position_type = "Calendar Spread"
                position_id = f"{position.short_option.symbol}_{position.long_option.symbol}"
                
                record_info = f"""
                === POSITION CLOSE RECORD ===
                Time: {timestamp}
                Position Type: {position_type}
                Position ID: {position_id}
                Close Reason: {close_reason}
                Contracts: {position.contracts}

                Options Info:
                Short Option: {position.short_option.symbol}
                    - Strike: ${position.short_option.strike:,.0f}
                    - Days to Expiry: {position.short_option.days_to_expiry}
                    - Entry IV: {getattr(position, 'short_option_entry_iv', 'N/A')}
                    - Current IV: {position.short_option.iv:.4f}
                    - Delta: {position.short_option.delta:+.4f}
                    
                Long Option: {position.long_option.symbol}
                    - Strike: ${position.long_option.strike:,.0f}
                    - Days to Expiry: {position.long_option.days_to_expiry}
                    - Entry IV: {getattr(position, 'long_option_entry_iv', 'N/A')}
                    - Current IV: {position.long_option.iv:.4f}
                    - Delta: {position.long_option.delta:+.4f}

                P&L Information:
                Unrealized P&L: {current_pnl:+.6f} BTC
                P&L Ratio: {current_pnl_ratio:+.2%}
                
                Strategy Information:
                IV Spread: {position.iv_spread:+.4f}
                Time Gap: {position.time_gap_days} days
                Net Premium: {position.net_premium:+.6f} BTC
                Signal Strength: {position.signal_strength}

                Environment: {env}
                {'='*50}

                """
            
            # 写入日志文件
            with open(position_close_log, 'a', encoding='utf-8') as f:
                f.write(record_info)
            
            print(f"📝 平仓信息已记录到: {position_close_log}")
            
        except Exception as e:
            print(f"❌ 记录平仓信息失败: {e}")


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
    
    def get_opened_opportunities_pnl(self, 
                                     opportunity: Union[StraddleOpportunity, CalendarSpreadOpportunity], 
                                     env: str = "testnet"):
        """
        获取已开仓opportunity的精确未实现P&L - 使用简化API
        
        Args:
            opportunity: 持仓机会对象
            env: 环境 ("testnet" 或 "mainnet")
            
        Returns:
            float: 精确未实现P&L (BTC)，获取失败返回0.0
        """
        try:
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
                return None, None
            
            # 🆕 使用简化的精确P&L获取 - 只取第一个合约的币种P&L
            # 假设同一策略的期权都是同一币种
            precise_pnl_1 = get_instrument_pnl(target_instruments[0], env)
            precise_pnl_2 = get_instrument_pnl(target_instruments[1], env)
            precise_pnl = precise_pnl_1 + precise_pnl_2


            contract_size = opportunity.contracts
            open_price_1 = get_instrument_open_price(target_instruments[0], env)
            open_price_2 = get_instrument_open_price(target_instruments[1], env)
            total_options_cost = open_price_1 * contract_size + open_price_2 * contract_size
            pnl_ratio = precise_pnl / total_options_cost



            self.logger.info(f"for instrument {target_instruments[0]}, pnl is {precise_pnl_1:.8f} BTC")
            self.logger.info(f"for instrument {target_instruments[1]}, pnl is {precise_pnl_2:.8f} BTC")
            self.logger.info(f"📊 {strategy_type} 精确P&L: {precise_pnl:.8f} BTC")
            self.logger.info(f"   数据来源: account_summary (简化API)")
            
            return precise_pnl, pnl_ratio
            
        except Exception as e:
            self.logger.error(f"❌ 获取精确P&L失败: {e}")
            return None, None 

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
            current_pnl, current_pnl_ratio = self.get_opened_opportunities_pnl(position, env)
            
            if current_pnl == None:
                return False, "无法获取P&L信息"

            # 根据策略类型调用对应的平仓检查方法
            if isinstance(position, StraddleOpportunity):
                return self._check_straddle_close_condition(position, current_pnl, current_pnl_ratio, env)
            elif isinstance(position, CalendarSpreadOpportunity):
                return self._check_calendar_close_condition(position, current_pnl, current_pnl_ratio, env)
            else:
                self.logger.error(f"❌ 未知的position类型: {type(position)}")
                return False, "未知策略类型"
                
        except Exception as e:
            self.logger.error(f"❌ 检查平仓条件失败: {e}")
            return False, f"检查失败: {e}"
        
    
    def monitor_positions(self, check_duration: str = "5min"):

        # convert check_duration to seconds
        check_duration = self._transform_check_duration(check_duration)
        
        while True:
            # get realize_vol
            current_realize_vol = self.realize_vol_extracter.predict()['realized_vol_annualized']
            total_net_delta = self.update_positions(current_realize_vol, self.env, None)  # 监控线程不记录平仓日志

            # 当前逻辑：无论Delta多小都会对冲
            hedge_delta_diff = -total_net_delta - self.current_hedged_delta

            # 建议：添加阈值检查
            if abs(hedge_delta_diff) > self.delta_hedge_threshold:
                self.hedge_action(hedge_delta_diff, self.env)
                self.current_hedged_delta = -total_net_delta

            time.sleep(check_duration)
    
    def _transform_check_duration(self, check_duration: str):
        if check_duration == "5min":
            check_duration = 300
        elif check_duration == "10min":
            check_duration = 600
        elif check_duration == "15min":
            check_duration = 900
        elif check_duration == "30min":
            check_duration = 1800
        else:
            raise ValueError(f"Invalid check duration: {check_duration}")

        return check_duration
    
    def _check_straddle_close_condition(self, position: StraddleOpportunity, current_pnl: float, current_pnl_ratio: float, env: str) -> Tuple[bool, str]:
        """
        Straddle策略平仓条件检查
        
        Args:
            position: Straddle持仓对象
            current_pnl: 当前P&L
            current_pnl_ratio: 当前P&L比例
            env: 交易环境
            
        Returns:
            tuple: (should_close: bool, reason: str)
        """
        # 1. 基础止损止盈检查
        if current_pnl_ratio < self.stop_loss_ratio:  # -30% 止损
            return True, f"Straddle止损 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"
        elif current_pnl_ratio > self.profit_target_ratio:  # +50% 止盈
            return True, f"Straddle止盈 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"
        
        # 2. IV反转检查 - 针对卖Straddle策略
        try:
            # 获取开仓时的IV
            entry_call_iv = position.call_option_entry_iv
            entry_put_iv = position.put_option_entry_iv
            entry_avg_iv = (entry_call_iv + entry_put_iv) / 2
            
            if entry_call_iv > 0 and entry_put_iv > 0:  # 确保有有效的entry IV
                # 直接使用当前IV数据（已在调用前更新）
                current_call_iv = position.call_option.iv
                current_put_iv = position.put_option.iv
                current_avg_iv = (current_call_iv + current_put_iv) / 2
                
                # 计算IV变化
                avg_iv_change = (current_avg_iv - entry_avg_iv) / entry_avg_iv
                call_iv_change = (current_call_iv - entry_call_iv) / entry_call_iv
                put_iv_change = (current_put_iv - entry_put_iv) / entry_put_iv
                
                self.logger.info(f"📊 Straddle IV变化分析:")
                self.logger.info(f"   平均IV: {entry_avg_iv:.4f} → {current_avg_iv:.4f} ({avg_iv_change:+.1%})")
                self.logger.info(f"   Call IV: {entry_call_iv:.4f} → {current_call_iv:.4f} ({call_iv_change:+.1%})")
                self.logger.info(f"   Put IV: {entry_put_iv:.4f} → {current_put_iv:.4f} ({put_iv_change:+.1%})")
                
                # 整体IV下降10% - 获利信号
                if avg_iv_change < -0.10:
                    return True, f"Straddle IV大幅下降获利平仓 (平均IV下降: {avg_iv_change:.1%})"
                
                # 任一端IV突然上涨10% - 风险信号  
                if call_iv_change > 0.10:
                    return True, f"Straddle Call IV剧烈上升风险平仓 (Call IV上涨: {call_iv_change:.1%})"
                
                if put_iv_change > 0.10:
                    return True, f"Straddle Put IV剧烈上升风险平仓 (Put IV上涨: {put_iv_change:.1%})"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Straddle IV反转检查失败: {e}")
        
        # 3. 价格变化检查
        try:
            # 获取开仓时的现货价格
            entry_spot_price = getattr(position, 'entry_spot_price', 0)
            
            if entry_spot_price > 0:
                # 获取当前现货价格
                currency = position.call_option.symbol.split('-')[0]  # BTC-28NOV25-114000-C -> BTC
                current_spot_price = get_index_price(currency, env)
                
                if current_spot_price > 0:
                    price_change_ratio = abs(current_spot_price - entry_spot_price) / entry_spot_price
                    
                    self.logger.info(f"📊 价格变化分析:")
                    self.logger.info(f"   开仓现货价: ${entry_spot_price:,.0f}")
                    self.logger.info(f"   当前现货价: ${current_spot_price:,.0f}")
                    self.logger.info(f"   价格变化: {price_change_ratio:+.1%}")
                    
                    if price_change_ratio > self.price_change_risk_ratio:
                        return True, f"价格变化过大风险平仓 (价格变化: {price_change_ratio:.1%}, 当前: ${current_spot_price:,.0f}, 开仓: ${entry_spot_price:,.0f})"
            
        except Exception as e:
            self.logger.warning(f"⚠️ 价格变化检查失败: {e}")
        
        # 4. 时间衰减保护
        try:
            # 从期权合约名解析到期日期
            from datetime import datetime
            
            def parse_option_expiry_date(symbol: str):
                """解析期权合约到期日期"""
                try:
                    # 从 "BTC-28NOV25-114000-C" 中提取 "28NOV25"
                    parts = symbol.split('-')
                    if len(parts) >= 2:
                        date_str = parts[1]  # "28NOV25"
                        # 解析日期格式 DDMMMYY
                        day = int(date_str[:2])  # 28
                        month_str = date_str[2:5]  # NOV
                        year = 2000 + int(date_str[5:])  # 2025
                        
                        # 月份映射
                        month_map = {
                            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                        }
                        month = month_map.get(month_str)
                        
                        if month:
                            return datetime(year, month, day).date()
                    return None
                except Exception:
                    return None
            
            # 解析Call期权的到期日期
            expiry_date = parse_option_expiry_date(position.call_option.symbol)
            
            if expiry_date:
                from datetime import datetime
                current_time = datetime.now()
                days_to_expiry = (expiry_date - current_time.date()).days
                
                self.logger.info(f"📅 时间衰减分析:")
                self.logger.info(f"   到期日期: {expiry_date}")
                self.logger.info(f"   剩余天数: {days_to_expiry}天")
                
                # 临近到期强制平仓
                if days_to_expiry <= 1:
                    return True, f"临近到期强制平仓 (剩余: {days_to_expiry}天)"
                
                # Short Straddle在最后2天时，如果盈利则考虑平仓锁定利润
                if "short" in position.strategy_type and days_to_expiry <= 2 and current_pnl_ratio > 0.1:
                    return True, f"Short Straddle临近到期获利平仓 (剩余: {days_to_expiry}天, P&L: {current_pnl_ratio*100:.1f}%)"
            
        except Exception as e:
            self.logger.warning(f"⚠️ 时间衰减检查失败: {e}")
        
        return False, f"Straddle继续持有 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"
    
    def _check_calendar_close_condition(self, position: CalendarSpreadOpportunity, current_pnl: float, current_pnl_ratio: float, env: str) -> Tuple[bool, str]:
        """
        Calendar Spread策略平仓条件检查
        
        Args:
            position: Calendar Spread持仓对象
            current_pnl: 当前P&L
            current_pnl_ratio: 当前P&L比例
            env: 交易环境
            
        Returns:
            tuple: (should_close: bool, reason: str)
        """
        # 1. 基础止损止盈检查
        if current_pnl_ratio < self.stop_loss_ratio:  # -30% 止损
            return True, f"Calendar止损 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"
        elif current_pnl_ratio > self.profit_target_ratio:  # +50% 止盈
            return True, f"Calendar止盈 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"
        
        # 2. IV价差反转检查 - 针对Calendar Spread策略
        try:
            # 获取开仓时的IV价差
            entry_short_iv = getattr(position, 'short_option_entry_iv', 0)
            entry_long_iv = getattr(position, 'long_option_entry_iv', 0)
            
            if entry_short_iv > 0 and entry_long_iv > 0:  # 确保有有效的entry IV
                entry_iv_spread = entry_short_iv - entry_long_iv
                
                # 直接使用当前IV数据（已在调用前更新）
                current_short_iv = position.short_option.iv
                current_long_iv = position.long_option.iv
                current_iv_spread = current_short_iv - current_long_iv
                
                self.logger.info(f"📊 Calendar IV价差分析:")
                self.logger.info(f"   开仓IV价差: {entry_iv_spread:+.4f}")
                self.logger.info(f"   当前IV价差: {current_iv_spread:+.4f}")
                self.logger.info(f"   Short IV: {entry_short_iv:.4f} → {current_short_iv:.4f}")
                self.logger.info(f"   Long IV: {entry_long_iv:.4f} → {current_long_iv:.4f}")
                
                # 如果入场时IV价差为正但现在变为负值，立即平仓
                if entry_iv_spread > 0 and current_iv_spread < -0.01:
                    return True, f"Calendar IV价差反转平仓 (入场: {entry_iv_spread:+.1%} → 当前: {current_iv_spread:+.1%})"
            else:
                # 回退到简单的IV价差检查
                iv_spread = position.short_option.iv - position.long_option.iv
                if iv_spread < -0.01: 
                    return True, f"IV价差反转平仓 (当前IV价差: {iv_spread:.1%})"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Calendar IV价差反转检查失败: {e}")
        
        # 3. Delta风险控制 (Calendar Spread使用更宽松的阈值)
        try:
            # 获取净Delta
            net_delta = getattr(position, 'net_delta', 0)
            if hasattr(position, 'long_option') and hasattr(position, 'short_option'):
                net_delta = position.long_option.delta - position.short_option.delta
            
            calendar_delta_threshold = self.delta_risk_threshold * 1.67  # 0.3 * 1.67 ≈ 0.5
            if abs(net_delta) > calendar_delta_threshold:
                return True, f"Calendar Delta风险过大 (净Delta: {net_delta:+.3f} > ±{calendar_delta_threshold:.1f})"
                
        except Exception as e:
            self.logger.warning(f"⚠️ Calendar Delta风险检查失败: {e}")
        
        # 4. 时间衰减保护 - 短期期权到期检查
        try:
            # 从期权合约名解析到期日期
            from datetime import datetime
            
            def parse_option_expiry_date(symbol: str):
                """解析期权合约到期日期"""
                try:
                    # 从 "BTC-28NOV25-114000-C" 中提取 "28NOV25"
                    parts = symbol.split('-')
                    if len(parts) >= 2:
                        date_str = parts[1]  # "28NOV25"
                        # 解析日期格式 DDMMMYY
                        day = int(date_str[:2])  # 28
                        month_str = date_str[2:5]  # NOV
                        year = 2000 + int(date_str[5:])  # 2025
                        
                        # 月份映射
                        month_map = {
                            'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
                            'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
                        }
                        month = month_map.get(month_str)
                        
                        if month:
                            return datetime(year, month, day).date()
                    return None
                except Exception:
                    return None
            
            # 解析短期期权的到期日期
            short_expiry_date = parse_option_expiry_date(position.short_option.symbol)
            
            if short_expiry_date:
                current_time = datetime.now()
                days_to_short_expiry = (short_expiry_date - current_time.date()).days
                
                self.logger.info(f"📅 Calendar时间衰减分析:")
                self.logger.info(f"   短期期权: {position.short_option.symbol}")
                self.logger.info(f"   短期到期日: {short_expiry_date}")
                self.logger.info(f"   剩余天数: {days_to_short_expiry}天")
                
                # 短期期权当天到期或已过期，立即平仓避免单腿风险
                if days_to_short_expiry <= 0:
                    return True, f"Calendar短期期权到期强制平仓 (短期期权剩余: {days_to_short_expiry}天，避免单腿风险)"
                
                # 短期期权还有1天到期，且P&L为负，平仓避免更大损失
                if days_to_short_expiry <= 1 and current_pnl_ratio < 0:
                    return True, f"Calendar短期期权即将到期且亏损平仓 (剩余: {days_to_short_expiry}天, P&L: {current_pnl_ratio*100:.1f}%)"
                
                # 短期期权还有1天到期，无论盈亏都考虑平仓（避免交割风险）
                if days_to_short_expiry <= 1:
                    return True, f"Calendar短期期权即将到期平仓 (剩余: {days_to_short_expiry}天，避免交割风险)"
            
        except Exception as e:
            self.logger.warning(f"⚠️ Calendar时间衰减检查失败: {e}")
        
        return False, f"Calendar继续持有 (P&L: {current_pnl_ratio*100:.1f}%, {current_pnl:.6f} BTC)"