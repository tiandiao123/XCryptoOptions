import time
import threading
import os
import json
from datetime import datetime
from typing import List, Union, Dict, Any
from qtrade.optionstrader.arbitrage_searcher.option_data import StraddleOpportunityOKX, CalendarSpreadOpportunity
from qtrade.optionstrader.arbitrage_searcher.calendar_spread_manager import CalendarArbitrageManagerOKX
from qtrade.optionstrader.arbitrage_searcher.gamma_scalping_manager import GammaScalpingManagerOKX
from qtrade.optionstrader.trading_engine.okx_engine.okx_risk_manager import OKXRiskManager, create_okx_risk_manager
from qtrade.order_api.okx.client.options_client import OKXOptionsClient


class OKXTradingEngine:
    """
    OKX期权交易引擎
    
    功能：
    - Calendar Spread策略搜索和执行
    - Gamma Scalping (Selling Straddle)策略搜索和执行
    - 持仓风险管理和监控
    - Delta对冲
    - P&L记录和可视化
    """
    
    def __init__(self, 
                 calendar_config_path: str, 
                 gamma_scalping_config_path: str,
                 symbol: str = "BTC-USD",
                 env: str = "testnet", 
                 max_open_calendar: int = 1,
                 max_open_gamma_scalping: int = 1,
                 enable_delta_hedge: bool = True,
                 stop_loss_ratio: float = -0.3,
                 profit_target_ratio: float = 0.5,
                 output_folder: str = "/home/ubuntu/options_trading/trading_results/okx"):
        """
        初始化OKX交易引擎
        
        Args:
            calendar_config_path: Calendar Spread配置文件路径
            gamma_scalping_config_path: Gamma Scalping配置文件路径
            symbol: 交易币种 (例如 "BTC-USD" 或 "ETH-USD")
            env: 交易环境 (testnet/mainnet)
            max_open_calendar: Calendar Spread最大持仓数量
            max_open_gamma_scalping: Gamma Scalping最大持仓数量
            enable_delta_hedge: 是否启用Delta对冲
            stop_loss_ratio: 止损比率（例如-0.3表示-30%）
            profit_target_ratio: 止盈比率（例如0.5表示50%）
            output_folder: 输出文件夹路径，用于存储图表和日志
        """
        self.env = env 
        self.symbol = symbol
        self.max_open_calendar = max_open_calendar
        self.max_open_gamma_scalping = max_open_gamma_scalping
        self.output_folder = output_folder
        
        # 初始化输出文件夹结构
        self._setup_output_folders()
        
        print(f"🚀 [OKX] TradingEngine初始化")
        print(f"   交易环境: {env}")
        print(f"   输出文件夹: {output_folder}")
        print(f"   图表文件夹: {self.charts_folder}")
        print(f"   日志文件夹: {self.logs_folder}")
        
        # 初始化策略管理器
        print(f"\n📊 初始化策略管理器...")
        self.calendar_spread_manager = CalendarArbitrageManagerOKX(calendar_config_path)
        # 从symbol提取currency (例如 "BTCUSDT" -> "BTC")
        currency = "BTC" if "BTC" in symbol else "ETH"
        self.gamma_scalping_manager = GammaScalpingManagerOKX(gamma_scalping_config_path, currency)
        
        # 初始化风险管理器
        print(f"\n🛡️ 初始化风险管理器...")
        self.risk_manager = create_okx_risk_manager(
            symbol="BTCUSDT",  # 用于波动率跟踪
            max_positions=max_open_calendar + max_open_gamma_scalping,
            enable_delta_hedge=enable_delta_hedge,
            stop_loss_ratio=stop_loss_ratio,
            profit_target_ratio=profit_target_ratio,
            env=env
        )
        
        # 初始化OKX Options Client用于下单
        print(f"\n📡 初始化OKX Options Client...")
        self.options_client = OKXOptionsClient(simulated=(env == "testnet"))
        
        print(f"\n✅ [OKX] TradingEngine初始化完成")
    
    def _setup_output_folders(self):
        """初始化输出文件夹结构"""
        try:
            # 创建主输出文件夹
            os.makedirs(self.output_folder, exist_ok=True)
            
            # 创建子文件夹
            self.charts_folder = os.path.join(self.output_folder, "charts")
            self.logs_folder = os.path.join(self.output_folder, "logs")
            
            os.makedirs(self.charts_folder, exist_ok=True)
            os.makedirs(self.logs_folder, exist_ok=True)
            
            # 设置文件路径
            self.pnl_data_file = os.path.join(self.logs_folder, "pnl_data.json")
            self.position_close_log = os.path.join(self.logs_folder, "position_closes.txt")
            
            print(f"📁 输出文件夹结构创建成功:")
            print(f"   主文件夹: {self.output_folder}")
            print(f"   图表文件夹: {self.charts_folder}")
            print(f"   日志文件夹: {self.logs_folder}")
            
        except Exception as e:
            print(f"❌ 创建输出文件夹失败: {e}")
            # 使用默认路径作为备用
            self.charts_folder = "/tmp/okx_charts"
            self.logs_folder = "/tmp/okx_logs"
            self.pnl_data_file = "/tmp/okx_pnl_data.json"
            self.position_close_log = "/tmp/okx_position_closes.txt"
            os.makedirs(self.charts_folder, exist_ok=True)
            os.makedirs(self.logs_folder, exist_ok=True)
    
    def _transform_check_duration(self, check_duration: str) -> int:
        """
        转换检查间隔字符串为秒数
        
        Args:
            check_duration: "5min", "10min", "15min", "30min", "1hour"
            
        Returns:
            秒数
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
    
    def _ranking_opportunities(self, opportunities: Union[List[StraddleOpportunityOKX], List[CalendarSpreadOpportunity]]):
        """
        对机会进行排序并返回最佳机会
        
        排序规则:
        - StraddleOpportunityOKX: 按 iv_premium (IV - realized_vol) 降序排序
        - CalendarSpreadOpportunity: 按 iv_spread (short-term-iv - long-term-iv) 降序排序
        
        Args:
            opportunities: 机会列表
            
        Returns:
            最佳机会，如果列表为空则返回None
        """
        if not opportunities:
            return None
        
        # 检查机会类型并进行相应排序
        if isinstance(opportunities[0], StraddleOpportunityOKX):
            # StraddleOpportunityOKX: 按 iv_premium 降序排序
            sorted_opportunities = sorted(
                opportunities, 
                key=lambda x: x.iv_premium,  # IV - realized_vol
                reverse=True  # 降序，最大的在前面
            )
            
            print(f"🎯 [OKX] Straddle机会排序完成:")
            for i, opp in enumerate(sorted_opportunities[:3], 1):  # 显示前3个
                print(f"   #{i}: ${opp.strike_price:,.0f} IV溢价={opp.iv_premium:.4f} "
                      f"(IV={opp.avg_iv:.4f} - RV={opp.realized_vol:.4f})")
            
        elif isinstance(opportunities[0], CalendarSpreadOpportunity):
            # CalendarSpreadOpportunity: 按 iv_spread 降序排序
            sorted_opportunities = sorted(
                opportunities,
                key=lambda x: x.iv_spread,  # short-term-iv - long-term-iv
                reverse=True  # 降序，最大的在前面
            )
            
            print(f"🎯 [OKX] Calendar Spread机会排序完成:")
            for i, opp in enumerate(sorted_opportunities[:3], 1):  # 显示前3个
                print(f"   #{i}: ${opp.short_option.strike:,.0f} IV价差={opp.iv_spread:.4f} "
                      f"时间间隔={opp.time_gap_days}天")
        
        else:
            raise ValueError(f"未知的机会类型: {type(opportunities[0])}")
        
        # 返回最佳机会
        best_opportunity = sorted_opportunities[0]
        
        if isinstance(best_opportunity, StraddleOpportunityOKX):
            print(f"✅ [OKX] 最佳Straddle机会: ${best_opportunity.strike_price:,.0f} "
                  f"IV溢价={best_opportunity.iv_premium:.4f}")
        elif isinstance(best_opportunity, CalendarSpreadOpportunity):
            print(f"✅ [OKX] 最佳Calendar机会: ${best_opportunity.short_option.strike:,.0f} "
                  f"IV价差={best_opportunity.iv_spread:.4f}")
        
        return best_opportunity 
    
    def _place_option_order(self, 
                            opportunity: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity], 
                            order_type: str = "market", 
                            crypto_amount: float = 0.1) -> Dict[str, Any]:
        """
        下期权订单 (OKX使用crypto notional)
        
        Args:
            opportunity: StraddleOpportunityOKX or CalendarSpreadOpportunity
            order_type: "market", "limit"
            crypto_amount: 加密货币数量 (例如 0.1 BTC 或 1.0 ETH)
            
        Returns:
            Dict with order results
        """
        assert order_type in ["market", "limit"], "order_type must be market or limit"
        assert crypto_amount > 0, "crypto_amount must be positive"

        order_results = []
        
        if isinstance(opportunity, StraddleOpportunityOKX):
            print(f"🎯 [OKX] 执行Straddle交易: ${opportunity.strike_price:,.0f}")
            print(f"   策略: {opportunity.strategy_type}")
            print(f"   数量: {crypto_amount} (crypto notional)")
            print(f"   订单类型: {order_type}")
            
            call_option = opportunity.call_option
            put_option = opportunity.put_option
            
            if order_type == "market":
                # Selling Straddle: 卖出Call和Put
                print(f"📤 卖出Call: {call_option.symbol}")
                try:
                    call_result = self.options_client.place_market_order_crypto_notional(
                        inst_id=call_option.symbol,
                        side="sell",
                        sz=str(crypto_amount)
                    )
                    success = call_result.get("sCode") == "0"
                    order_results.append({
                        "type": "call",
                        "side": "sell",
                        "result": call_result,
                        "success": success
                    })
                    if success:
                        print(f"   ✅ Call订单成功: {call_result.get('data', [{}])[0].get('ordId', 'N/A')}")
                    else:
                        print(f"   ❌ Call订单失败: {call_result.get('sMsg', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ Call订单异常: {e}")
                    order_results.append({
                        "type": "call",
                        "side": "sell",
                        "result": {"error": str(e)},
                        "success": False
                    })
                
                print(f"📤 卖出Put: {put_option.symbol}")
                try:
                    put_result = self.options_client.place_market_order_crypto_notional(
                        inst_id=put_option.symbol,
                        side="sell",
                        sz=str(crypto_amount)
                    )
                    success = put_result.get("sCode") == "0"
                    order_results.append({
                        "type": "put",
                        "side": "sell",
                        "result": put_result,
                        "success": success
                    })
                    if success:
                        print(f"   ✅ Put订单成功: {put_result.get('data', [{}])[0].get('ordId', 'N/A')}")
                    else:
                        print(f"   ❌ Put订单失败: {put_result.get('sMsg', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ Put订单异常: {e}")
                    order_results.append({
                        "type": "put",
                        "side": "sell",
                        "result": {"error": str(e)},
                        "success": False
                    })
                
            elif order_type == "limit":
                # TODO: 实现限价单逻辑
                print("⚠️ [OKX] 限价单功能待实现")
                return {"success": False, "error": "Limit order not implemented yet"}
                
        elif isinstance(opportunity, CalendarSpreadOpportunity):
            print(f"🎯 [OKX] 执行Calendar Spread交易:")
            print(f"   短期期权: {opportunity.short_option.symbol}")
            print(f"   长期期权: {opportunity.long_option.symbol}")
            print(f"   IV价差: {opportunity.iv_spread:.4f}")
            print(f"   数量: {crypto_amount} (crypto notional)")
            print(f"   订单类型: {order_type}")
            
            short_option = opportunity.short_option
            long_option = opportunity.long_option
            
            if order_type == "market":
                # Calendar Spread: 卖出短期，买入长期
                print(f"📤 卖出短期期权: {short_option.symbol}")
                try:
                    short_result = self.options_client.place_market_order_crypto_notional(
                        inst_id=short_option.symbol,
                        side="sell",
                        sz=str(crypto_amount)
                    )
                    success = short_result.get("sCode") == "0"
                    order_results.append({
                        "type": "short",
                        "side": "sell",
                        "result": short_result,
                        "success": success
                    })
                    if success:
                        print(f"   ✅ 短期订单成功: {short_result.get('data', [{}])[0].get('ordId', 'N/A')}")
                    else:
                        print(f"   ❌ 短期订单失败: {short_result.get('sMsg', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ 短期订单异常: {e}")
                    order_results.append({
                        "type": "short",
                        "side": "sell",
                        "result": {"error": str(e)},
                        "success": False
                    })
                
                print(f"📥 买入长期期权: {long_option.symbol}")
                try:
                    long_result = self.options_client.place_market_order_crypto_notional(
                        inst_id=long_option.symbol,
                        side="buy",
                        sz=str(crypto_amount)
                    )
                    success = long_result.get("sCode") == "0"
                    order_results.append({
                        "type": "long",
                        "side": "buy",
                        "result": long_result,
                        "success": success
                    })
                    if success:
                        print(f"   ✅ 长期订单成功: {long_result.get('data', [{}])[0].get('ordId', 'N/A')}")
                    else:
                        print(f"   ❌ 长期订单失败: {long_result.get('sMsg', 'Unknown error')}")
                except Exception as e:
                    print(f"   ❌ 长期订单异常: {e}")
                    order_results.append({
                        "type": "long",
                        "side": "buy",
                        "result": {"error": str(e)},
                        "success": False
                    })
                
            elif order_type == "limit":
                # TODO: 实现限价单逻辑
                print("⚠️ [OKX] 限价单功能待实现")
                return {"success": False, "error": "Limit order not implemented yet"}
        
        # 汇总结果
        success_count = sum(1 for order in order_results if order.get("success", False))
        total_orders = len(order_results)
        
        result = {
            "success": success_count == total_orders,
            "total_orders": total_orders,
            "successful_orders": success_count,
            "failed_orders": total_orders - success_count,
            "order_details": order_results,
            "opportunity_type": type(opportunity).__name__,
            "strategy_info": {
                "strike_price": getattr(opportunity, 'strike_price', 
                                      getattr(opportunity.short_option, 'strike', 0) if hasattr(opportunity, 'short_option') else 0),
                "crypto_amount": crypto_amount,
                "order_type": order_type
            }
        }
        
        if result["success"]:
            opportunity.open_status = True
            opportunity.contracts = crypto_amount
            
            # 记录开仓时的IV信息
            self._record_entry_iv(opportunity)
            
            print(f"✅ [OKX] 所有订单执行成功 ({success_count}/{total_orders})")
        else:
            print(f"❌ [OKX] 部分订单执行失败 ({success_count}/{total_orders})")
            for order in order_results:
                if not order.get("success", False):
                    error_msg = order["result"].get("sMsg", order["result"].get("error", "Unknown error"))
                    print(f"   失败订单: {order['type']} {order['side']} - {error_msg}")
            
        return result

    def _record_entry_iv(self, opportunity: Union[StraddleOpportunityOKX, CalendarSpreadOpportunity]) -> None:
        """
        记录开仓时的IV信息
        
        Args:
            opportunity: StraddleOpportunityOKX or CalendarSpreadOpportunity
        """
        try:
            if isinstance(opportunity, StraddleOpportunityOKX):
                # 记录Straddle的Call和Put开仓IV
                opportunity.call_option_entry_iv = opportunity.call_option.iv
                opportunity.put_option_entry_iv = opportunity.put_option.iv
                opportunity.entry_spot_price = opportunity.spot_price
                
                print(f"📊 [OKX] 记录Straddle开仓信息:")
                print(f"   Call IV: {opportunity.call_option_entry_iv:.4f}")
                print(f"   Put IV: {opportunity.put_option_entry_iv:.4f}")
                print(f"   平均IV: {(opportunity.call_option_entry_iv + opportunity.put_option_entry_iv)/2:.4f}")
                print(f"   开仓现货价: ${opportunity.entry_spot_price:,.0f}")
                
            elif isinstance(opportunity, CalendarSpreadOpportunity):
                # 记录Calendar Spread的Short和Long开仓IV
                opportunity.short_option_entry_iv = opportunity.short_option.iv
                opportunity.long_option_entry_iv = opportunity.long_option.iv
                
                print(f"📊 [OKX] 记录Calendar Spread开仓IV:")
                print(f"   Short IV: {opportunity.short_option_entry_iv:.4f}")
                print(f"   Long IV: {opportunity.long_option_entry_iv:.4f}")
                print(f"   IV价差: {opportunity.short_option_entry_iv - opportunity.long_option_entry_iv:.4f}")
                    
        except Exception as e:
            print(f"❌ [OKX] 记录开仓IV失败: {e}")

    def run_loop(self, check_duration: str = "5min", order_type: str = "market", crypto_amount: float = 0.1):
        """
        主交易循环
        
        Args:
            check_duration: "5min", "10min", "15min", "30min", "1hour"
            order_type: "market", "limit"
            crypto_amount: 每次交易的加密货币数量 (例如 0.1 BTC 或 1.0 ETH)
        """
        
        valid_durations = ["5min", "10min", "15min", "30min", "1hour"]
        assert check_duration in valid_durations, f"check_duration must be one of {valid_durations}"
        
        check_interval_seconds = self._transform_check_duration(check_duration)

        print(f"\n🚀 [OKX] 启动交易引擎循环")
        print(f"   检查间隔: {check_duration} ({check_interval_seconds}秒)")
        print(f"   订单类型: {order_type}")
        print(f"   交易数量: {crypto_amount} (crypto notional)")
        print(f"   最大Calendar持仓: {self.max_open_calendar}")
        print(f"   最大Gamma Scalping持仓: {self.max_open_gamma_scalping}")

        # 创建持仓监控线程
        monitoring_thread = threading.Thread(
            target=self._start_position_monitoring,
            args=(check_duration,),
            daemon=True,
            name="OKX_PositionMonitor"
        )
        monitoring_thread.start()
        print(f"\n🔍 [OKX] 持仓监控线程已启动")
        print(f"   线程名: {monitoring_thread.name}")
        print(f"   线程ID: {monitoring_thread.ident}")
        print(f"   监控间隔: {check_duration}")

        # 创建P&L记录线程
        pnl_recording_thread = threading.Thread(
            target=self._start_pnl_recording,
            args=(check_interval_seconds,),
            daemon=True,
            name="OKX_PnLRecorder"
        )
        pnl_recording_thread.start()
        print(f"\n📊 [OKX] P&L记录线程已启动")
        print(f"   线程名: {pnl_recording_thread.name}")
        print(f"   线程ID: {pnl_recording_thread.ident}")
        print(f"   记录间隔: {check_interval_seconds}秒")

        
        while True:
            try:
                print(f"\n{'='*70}")
                print(f"🔍 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [OKX] 检查交易机会...")
                print(f"{'='*70}")
                
                # 检查机会
                calendar_opportunities = self.calendar_spread_manager.check_opportunities()
                gamma_scalping_opportunities = self.gamma_scalping_manager.check_opportunities()
                
                # 处理Calendar Spread机会
                position_counts = self.risk_manager.get_position_count()
                if position_counts["calendar_spread"] < self.max_open_calendar: 
                    if calendar_opportunities and len(calendar_opportunities) > 0:
                        print(f"\n📊 [OKX] 发现 {len(calendar_opportunities)} 个Calendar Spread机会")
                        best_calendar_opportunity = self._ranking_opportunities(calendar_opportunities)
                        
                        if best_calendar_opportunity:
                            print(f"\n🎯 [OKX] 执行最佳Calendar Spread机会")
                            order_result = self._place_option_order(
                                best_calendar_opportunity, 
                                order_type, 
                                crypto_amount
                            )
                            
                            if order_result["success"]:
                                self.risk_manager.add_position(best_calendar_opportunity)
                                updated_counts = self.risk_manager.get_position_count()
                                print(f"✅ [OKX] Calendar Spread交易成功，当前持仓: {updated_counts['calendar_spread']}")
                            else:
                                print(f"❌ [OKX] Calendar Spread交易失败")
                    else:
                        print(f"\n📊 [OKX] 未发现Calendar Spread机会")
                else:
                    print(f"\n📊 [OKX] Calendar Spread持仓已满 ({position_counts['calendar_spread']}/{self.max_open_calendar})")

                # 处理Gamma Scalping机会
                position_counts = self.risk_manager.get_position_count()  # 重新获取最新计数
                if position_counts["straddle"] < self.max_open_gamma_scalping:
                    if gamma_scalping_opportunities and len(gamma_scalping_opportunities) > 0:
                        print(f"\n📊 [OKX] 发现 {len(gamma_scalping_opportunities)} 个Gamma Scalping机会")
                        best_gamma_scalping_opportunity = self._ranking_opportunities(gamma_scalping_opportunities)
                        
                        if best_gamma_scalping_opportunity:
                            print(f"\n🎯 [OKX] 执行最佳Gamma Scalping机会")
                            order_result = self._place_option_order(
                                best_gamma_scalping_opportunity, 
                                order_type,
                                crypto_amount
                            )
                            
                            if order_result["success"]:
                                self.risk_manager.add_position(best_gamma_scalping_opportunity)
                                updated_counts = self.risk_manager.get_position_count()
                                print(f"✅ [OKX] Gamma Scalping交易成功，当前持仓: {updated_counts['straddle']}")
                            else:
                                print(f"❌ [OKX] Gamma Scalping交易失败")
                    else:
                        print(f"\n📊 [OKX] 未发现Gamma Scalping机会")
                else:
                    print(f"\n📊 [OKX] Gamma Scalping持仓已满 ({position_counts['straddle']}/{self.max_open_gamma_scalping})")
                
                print(f"\n⏰ [OKX] 等待 {check_interval_seconds}秒 后进行下次检查...")
                time.sleep(check_interval_seconds)
                
            except KeyboardInterrupt:
                print("\n🛑 [OKX] 收到中断信号，停止交易循环")
                break
            except Exception as e:
                print(f"❌ [OKX] 交易循环出错: {e}")
                import traceback
                traceback.print_exc()
                print("⏰ 等待60秒后继续...")
                time.sleep(60)
    
    def record_pnl(self, record_interval: int = 300):
        """
        定期记录账户equity信息并绘制曲线图 (OKX版本)
        
        Args:
            record_interval: 记录间隔（秒），默认300秒（5分钟）
        """
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        
        try:
            print(f"🚀 [OKX] 启动P&L记录线程")
            print(f"   记录间隔: {record_interval}秒 ({record_interval//60}分钟)")
            print(f"   交易环境: {self.env}")
            print(f"   图表保存路径: {self.charts_folder}")
            print(f"   数据保存路径: {self.pnl_data_file}")
            
            initial_equity = None
            pnl_history = []
            
            # 尝试加载历史数据
            if os.path.exists(self.pnl_data_file):
                try:
                    with open(self.pnl_data_file, 'r') as f:
                        saved_data = json.load(f)
                        initial_equity = saved_data.get('initial_equity')
                        pnl_history = saved_data.get('history', [])
                    print(f"📊 [OKX] 加载历史P&L数据: {len(pnl_history)}条记录")
                    if initial_equity:
                        print(f"   初始Equity: ${initial_equity:,.2f} USDT")
                except Exception as e:
                    print(f"⚠️ [OKX] 加载历史数据失败: {e}")
            
            while True:
                try:
                    current_time = datetime.now()
                    timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S')
                    
                    # 获取OKX账户信息
                    # TODO: 实现OKX的账户余额获取
                    # 暂时使用占位符
                    current_equity = 10000.0  # 占位符，需要实现实际的OKX余额获取
                    
                    # 设置初始equity
                    if initial_equity is None:
                        initial_equity = current_equity
                        print(f"📊 [OKX] 设置初始Equity: ${initial_equity:,.2f} USDT")
                    
                    # 计算相对P&L
                    relative_pnl = current_equity - initial_equity
                    
                    # 记录数据
                    record = {
                        "timestamp": timestamp,
                        "equity": current_equity,
                        "relative_pnl": relative_pnl,
                        "datetime": current_time.isoformat()
                    }
                    pnl_history.append(record)
                    
                    print(f"📊 [OKX] [{timestamp}] Equity记录:")
                    print(f"   当前Equity: ${current_equity:,.2f} USDT")
                    print(f"   相对P&L: ${relative_pnl:+,.2f} USDT")
                    print(f"   相对P&L%: {(relative_pnl/initial_equity*100):+.2f}%")
                    
                    # 保存数据到文件
                    data_to_save = {
                        "initial_equity": initial_equity,
                        "history": pnl_history,
                        "last_update": timestamp
                    }
                    
                    with open(self.pnl_data_file, 'w') as f:
                        json.dump(data_to_save, f, indent=2)
                    
                    # 每10条记录或每小时更新一次图表
                    if len(pnl_history) % 10 == 0 or len(pnl_history) % (3600//record_interval) == 0:
                        self._update_equity_chart(pnl_history, initial_equity)
                    
                    time.sleep(record_interval)
                    
                except KeyboardInterrupt:
                    print(f"🛑 [OKX] P&L记录线程收到中断信号")
                    break
                except Exception as e:
                    print(f"❌ [OKX] P&L记录出错: {e}")
                    time.sleep(60)  # 出错后等待1分钟再继续
                    
        except Exception as e:
            print(f"❌ [OKX] P&L记录线程启动失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _update_equity_chart(self, pnl_history: List[Dict], initial_equity: float):
        """更新equity曲线图 (OKX版本)"""
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
            from datetime import datetime
            
            if len(pnl_history) < 2:
                return
            
            # 准备数据
            timestamps = []
            relative_pnls = []
            
            for record in pnl_history:
                timestamps.append(datetime.fromisoformat(record['datetime']))
                relative_pnls.append(record['relative_pnl'])
            
            # 创建图表
            plt.figure(figsize=(12, 8))
            
            # 绘制相对P&L曲线
            plt.subplot(2, 1, 1)
            plt.plot(timestamps, relative_pnls, 'b-', linewidth=2, label='Relative P&L (USDT)')
            plt.axhline(y=0, color='gray', linestyle='--', alpha=0.7)
            plt.title(f'OKX Options Trading Equity Curve (Initial: ${initial_equity:,.2f} USDT)', 
                     fontsize=14, fontweight='bold')
            plt.ylabel('Relative P&L (USDT)', fontsize=12)
            plt.grid(True, alpha=0.3)
            plt.legend()
            
            # 设置x轴格式
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
            plt.xticks(rotation=45)
            
            # 绘制百分比P&L曲线
            plt.subplot(2, 1, 2)
            relative_pnl_pct = [(pnl/initial_equity*100) for pnl in relative_pnls]
            plt.plot(timestamps, relative_pnl_pct, 'g-', linewidth=2, label='Relative P&L (%)')
            plt.axhline(y=0, color='gray', linestyle='--', alpha=0.7)
            plt.ylabel('Relative P&L (%)', fontsize=12)
            plt.xlabel('Time', fontsize=12)
            plt.grid(True, alpha=0.3)
            plt.legend()
            
            # 设置x轴格式
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
            plt.gca().xaxis.set_major_locator(mdates.HourLocator(interval=1))
            plt.xticks(rotation=45)
            
            # 调整布局
            plt.tight_layout()
            
            # 保存图表
            chart_filename = os.path.join(self.charts_folder, 
                                         f"okx_equity_curve_{datetime.now().strftime('%Y%m%d')}.png")
            plt.savefig(chart_filename, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"📈 [OKX] Equity曲线图已更新: {chart_filename}")
            
        except Exception as e:
            print(f"❌ [OKX] 更新Equity图表失败: {e}")
    
    def _start_pnl_recording(self, record_interval: int):
        """启动P&L记录的独立线程"""
        try:
            print(f"🚀 [OKX] P&L记录线程启动")
            print(f"   记录间隔: {record_interval}秒")
            print(f"   线程ID: {threading.current_thread().ident}")
            print(f"   线程名: {threading.current_thread().name}")
            
            # 调用record_pnl方法
            self.record_pnl(record_interval)
            
        except KeyboardInterrupt:
            print(f"🛑 [OKX] P&L记录线程收到中断信号")
        except Exception as e:
            print(f"❌ [OKX] P&L记录线程出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _start_position_monitoring(self, check_duration: str):
        """
        启动持仓监控的独立线程
        
        Args:
            check_duration: 检查间隔 ("5min", "10min", "15min", "30min", "1hour")
        """
        try:
            print(f"🚀 [OKX] 持仓监控线程启动")
            print(f"   监控间隔: {check_duration}")
            print(f"   线程ID: {threading.current_thread().ident}")
            print(f"   线程名: {threading.current_thread().name}")
            print(f"   Delta对冲: {'启用' if self.risk_manager.enable_delta_hedge else '禁用'}")
            
            # 调用RiskManager的监控方法
            self.risk_manager.monitor_positions(check_duration=check_duration)
            
        except KeyboardInterrupt:
            print(f"🛑 [OKX] 持仓监控线程收到中断信号")
        except Exception as e:
            print(f"❌ [OKX] 持仓监控线程出错: {e}")
            import traceback
            traceback.print_exc()


def create_okx_trading_engine(
    calendar_config_path: str,
    gamma_scalping_config_path: str,
    symbol: str = "BTC-USD",
    env: str = "testnet",
    max_open_calendar: int = 1,
    max_open_gamma_scalping: int = 1,
    enable_delta_hedge: bool = True,
    stop_loss_ratio: float = -0.3,
    profit_target_ratio: float = 0.5,
    output_folder: str = "/home/ubuntu/options_trading/trading_results/okx"
) -> OKXTradingEngine:
    """
    创建OKX交易引擎的工厂函数
    
    Args:
        calendar_config_path: Calendar Spread配置文件路径
        gamma_scalping_config_path: Gamma Scalping配置文件路径
        symbol: 交易币种 (例如 "BTC-USD" 或 "ETH-USD")
        env: 交易环境 (testnet/mainnet)
        max_open_calendar: Calendar Spread最大持仓数量
        max_open_gamma_scalping: Gamma Scalping最大持仓数量
        enable_delta_hedge: 是否启用Delta对冲
        stop_loss_ratio: 止损比率
        profit_target_ratio: 止盈比率
        output_folder: 输出文件夹路径
        
    Returns:
        OKXTradingEngine实例
    """
    return OKXTradingEngine(
        calendar_config_path=calendar_config_path,
        gamma_scalping_config_path=gamma_scalping_config_path,
        symbol=symbol,
        env=env,
        max_open_calendar=max_open_calendar,
        max_open_gamma_scalping=max_open_gamma_scalping,
        enable_delta_hedge=enable_delta_hedge,
        stop_loss_ratio=stop_loss_ratio,
        profit_target_ratio=profit_target_ratio,
        output_folder=output_folder
    )

