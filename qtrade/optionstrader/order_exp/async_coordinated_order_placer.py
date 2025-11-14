#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar Spread异步协同下单策略
使用asyncio实现真正的并发监控和快速响应
"""

import asyncio
import time
from typing import Dict, Any, Optional, Tuple, Literal
from dataclasses import dataclass

from qtrade.order_api.okx.client.options_client import OKXOptionsClient
from qtrade.optionstrader.arbitrage_searcher.option_data import CalendarSpreadOpportunity


Side = Literal["buy", "sell"]


@dataclass
class OrderSpec:
    """订单规格"""
    symbol: str
    side: Side
    crypto_notional: float
    price_offset_ticks: int = 1
    post_only: bool = True


@dataclass
class ActiveOrder:
    """活跃订单状态"""
    order_id: str
    symbol: str
    side: Side
    price: float
    sz: int
    filled_sz: int = 0
    avg_px: float = 0.0
    status: str = "live"  # live/partially_filled/filled/canceled


class OKXAsyncAPI:
    """
    OKX异步API适配器
    将同步的OKXOptionsClient包装为异步接口
    """
    
    def __init__(self, client: OKXOptionsClient):
        self.client = client
        self.tick_size: Dict[str, float] = {}
        self._order_cache: Dict[str, ActiveOrder] = {}  # 订单缓存，用于inst_id查找
        self._tick_size_cache: Dict[str, float] = {}
    
    async def get_tick_size(self, symbol: str) -> float:
        """获取tick size（带缓存）"""
        if symbol in self._tick_size_cache:
            return self._tick_size_cache[symbol]
        
        # 在线程池中执行同步调用
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, self.client.get_instrument_info, symbol)
        
        if info:
            tick_sz = float(info.get("tickSz", 0.0001))
            self._tick_size_cache[symbol] = tick_sz
            return tick_sz
        
        return 0.0001  # 默认值
    
    async def best_bid_ask(self, symbol: str) -> Tuple[float, float]:
        """获取最优买卖价"""
        loop = asyncio.get_event_loop()
        book = await loop.run_in_executor(None, self.client.get_orderbook, symbol)
        
        if not book:
            raise RuntimeError(f"Cannot get orderbook for {symbol}")
        
        return (book["bid"], book["ask"])
    
    def to_tick_price(self, symbol: str, px: float, tick_sz: float) -> float:
        """对齐到tick价格"""
        return round(round(px / tick_sz) * tick_sz, 10)
    
    async def place_limit(
        self,
        symbol: str,
        side: Side,
        sz: int,
        price: float,
        post_only: bool = True
    ) -> ActiveOrder:
        """挂限价单"""
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self.client.place_limit_order,
            symbol, side, sz, price, False, None
        )
        
        if not result.get("success"):
            raise RuntimeError(f"Order failed: {result.get('error')}")
        
        order = ActiveOrder(
            order_id=result["ordId"],
            symbol=symbol,
            side=side,
            price=price,
            sz=sz,
            status="live"
        )
        
        # 缓存订单信息，用于后续查询
        self._order_cache[result["ordId"]] = order
        
        return order
    
    async def place_aggressive(
        self,
        symbol: str,
        side: Side,
        sz: int,
        max_slippage_ticks: int = 2
    ) -> ActiveOrder:
        """
        强制成交（使用保守的限价单策略）
        
        策略：
        - 买单：使用 bid+1 (买一价+1tick)，接近但不超过卖盘
        - 卖单：使用 ask-1 (卖一价-1tick)，接近但不低于买盘
        
        优势：
        1. 比市价单更可控，避免过度滑点
        2. 比激进策略更保守，成交成本更低
        3. 成交概率仍然很高
        """
        loop = asyncio.get_event_loop()
        
        # 1. 获取当前盘口
        orderbook = await loop.run_in_executor(
            None,
            self.client.get_orderbook,
            symbol
        )
        
        if not orderbook:
            raise RuntimeError(f"Failed to get orderbook for {symbol}")
        
        # 2. 获取tick size
        inst_info = await loop.run_in_executor(
            None,
            self.client.get_instrument_info,
            symbol
        )
        
        tick_sz = float(inst_info.get("tickSz", 0.0001))
        
        # 3. 计算激进价格（保守策略）
        if side == "buy":
            # 买单：用 bid+1 (买一价+1tick)，在买盘上方但不超过卖盘
            aggressive_price = orderbook["bid"] + tick_sz
            price_desc = f"bid+1tick ({orderbook['bid']:.4f} + {tick_sz:.4f})"
        else:
            # 卖单：用 ask-1 (卖一价-1tick)，在卖盘下方但不低于买盘
            aggressive_price = orderbook["ask"] - tick_sz
            price_desc = f"ask-1tick ({orderbook['ask']:.4f} - {tick_sz:.4f})"
        
        print(f"   💥 激进价格: {aggressive_price:.4f} ({price_desc})")
        
        # 4. 下限价单（不使用post_only，确保能成交）
        result = await loop.run_in_executor(
            None,
            self.client.place_limit_order,
            symbol, side, sz, aggressive_price,
            False,  # post_only=False (允许taker)
            None    # cl_ord_id
        )
        
        if not result.get("success"):
            raise RuntimeError(f"Aggressive order failed: {result.get('error')}")
        
        order = ActiveOrder(
            order_id=result["ordId"],
            symbol=symbol,
            side=side,
            price=aggressive_price,
            sz=sz,
            status="live"
        )
        
        # 缓存订单信息，用于后续查询
        self._order_cache[result["ordId"]] = order
        
        return order
    
    async def cancel(self, symbol: str, order_id: str) -> None:
        """撤单"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self.client.cancel_order,
            symbol, order_id, None
        )
    
    async def get_order(self, order_id: str, inst_id: Optional[str] = None) -> ActiveOrder:
        """
        查询订单状态
        
        Args:
            order_id: 订单ID
            inst_id: 合约ID (如果不提供，从内部缓存查找)
        """
        loop = asyncio.get_event_loop()
        
        # 如果没有提供inst_id，尝试从已有订单中查找
        if not inst_id:
            # 从已下订单中查找inst_id
            for stored_order in self._order_cache.values():
                if stored_order.order_id == order_id:
                    inst_id = stored_order.symbol
                    break
        
        if not inst_id:
            print(f"   ⚠️ 无法查询订单 {order_id}: inst_id未知")
            return ActiveOrder(
                order_id=order_id,
                symbol="",
                side="buy",
                price=0.0,
                sz=0,
                status="unknown"
            )
        
        order_info = await loop.run_in_executor(
            None,
            self.client.get_order_details,
            inst_id,
            order_id
        )
        
        if not order_info:
            # 如果查询失败，返回未知状态
            return ActiveOrder(
                order_id=order_id,
                symbol=inst_id,
                side="buy",
                price=0.0,
                sz=0,
                status="unknown"
            )
        
        # 安全转换：处理空字符串和None
        def safe_float(value, default=0.0):
            if not value or value == '':
                return default
            return float(value)
        
        def safe_int(value, default=0):
            if not value or value == '':
                return default
            try:
                return int(float(value))
            except:
                return default
        
        return ActiveOrder(
            order_id=order_info["ordId"],
            symbol=order_info["instId"],
            side=order_info["side"],
            price=safe_float(order_info.get("px")),
            sz=safe_int(order_info.get("sz")),
            filled_sz=safe_int(order_info.get("accFillSz")),
            avg_px=safe_float(order_info.get("avgPx")),
            status=order_info["state"]
        )


class AsyncCalendarSpreadCoordinator:
    """
    异步Calendar Spread协同下单器
    
    核心特性：
    1. 使用asyncio并发监控两腿订单
    2. 任一腿触发立即响应（无轮询延迟）
    3. 快速撤单和市价成交
    """
    
    def __init__(
        self,
        client: OKXOptionsClient,
        opportunity: CalendarSpreadOpportunity,
        crypto_notional: float,
        price_offset_ticks: int = 1,
        trigger_fill_ratio: float = 1.0,
        max_slippage_ticks: int = 2,
        cancel_timeout: float = 3.0,
        poll_interval: float = 0.3
    ):
        """
        初始化异步协调器
        
        Args:
            client: OKX期权客户端
            opportunity: Calendar Spread机会
            crypto_notional: 交易数量（币本位）
            price_offset_ticks: 价格偏移（tick数量）
            trigger_fill_ratio: 触发比率（0-1）
            max_slippage_ticks: 最大滑点（tick数量）
            cancel_timeout: 撤单超时
            poll_interval: 轮询间隔
        """
        self.api = OKXAsyncAPI(client)
        self.opp = opportunity
        self.crypto_notional = crypto_notional
        self.price_offset_ticks = price_offset_ticks
        self.trigger_fill_ratio = trigger_fill_ratio
        self.max_slippage_ticks = max_slippage_ticks
        self.cancel_timeout = cancel_timeout
        self.poll_interval = poll_interval
        
        # 状态跟踪
        self._done = asyncio.Event()
        self._lock = asyncio.Lock()
        self._winner: Optional[str] = None  # "short" or "long"
        self._orders: Dict[str, ActiveOrder] = {}
        
        # 统计
        self.start_time: float = 0
        self.trigger_time: float = 0
    
    async def _price_for_passive(self, spec: OrderSpec) -> float:
        """计算被动挂单价格"""
        bb, ba = await self.api.best_bid_ask(spec.symbol)
        tick_sz = await self.api.get_tick_size(spec.symbol)
        
        if spec.side == "sell":
            # 卖单：略低于ask
            px = ba - (spec.price_offset_ticks * tick_sz)
        else:
            # 买单：略高于bid
            px = bb + (spec.price_offset_ticks * tick_sz)
        
        # 确保在bid-ask之间
        px = max(bb, min(px, ba))
        
        return self.api.to_tick_price(spec.symbol, px, tick_sz)
    
    async def _place_both_legs(self) -> Tuple[ActiveOrder, ActiveOrder]:
        """同时挂出两腿限价单"""
        currency = self.opp.short_option.symbol.split("-")[0]
        
        print(f"\n{'='*70}")
        print(f"🎯 [Async Calendar Spread] 开始协同下单")
        print(f"{'='*70}")
        print(f"📊 交易对:")
        print(f"   Short (卖出): {self.opp.short_option.symbol}")
        print(f"   Long (买入):  {self.opp.long_option.symbol}")
        print(f"   数量: {self.crypto_notional} {currency}")
        print(f"   策略: 异步并发监控")
        
        # 准备订单规格
        short_spec = OrderSpec(
            symbol=self.opp.short_option.symbol,
            side="sell",
            crypto_notional=self.crypto_notional,
            price_offset_ticks=self.price_offset_ticks
        )
        
        long_spec = OrderSpec(
            symbol=self.opp.long_option.symbol,
            side="buy",
            crypto_notional=self.crypto_notional,
            price_offset_ticks=self.price_offset_ticks
        )
        
        # 计算sz和价格
        short_sz = self.api.client._contracts_from_crypto_notional(
            short_spec.symbol,
            short_spec.crypto_notional
        )
        long_sz = self.api.client._contracts_from_crypto_notional(
            long_spec.symbol,
            long_spec.crypto_notional
        )
        
        short_px = await self._price_for_passive(short_spec)
        long_px = await self._price_for_passive(long_spec)
        
        print(f"\n📝 挂单价格:")
        print(f"   Short: {short_px:.4f} {currency} (sz={short_sz})")
        print(f"   Long:  {long_px:.4f} {currency} (sz={long_sz})")
        
        # 并发挂出两腿
        print(f"\n📤 并发挂出两腿订单...")
        
        try:
            short_order, long_order = await asyncio.gather(
                self.api.place_limit(short_spec.symbol, "sell", short_sz, short_px),
                self.api.place_limit(long_spec.symbol, "buy", long_sz, long_px)
            )
            
            self._orders["short"] = short_order
            self._orders["long"] = long_order
            
            print(f"   ✅ Short订单: {short_order.order_id}")
            print(f"   ✅ Long订单: {long_order.order_id}")
            print(f"✅ 两腿挂单完成，开始异步监控...")
            
            return short_order, long_order
            
        except Exception as e:
            print(f"❌ 挂单失败: {e}")
            # 如果有一腿成功，需要撤销
            if "short" in self._orders:
                await self.api.cancel(short_spec.symbol, self._orders["short"].order_id)
            if "long" in self._orders:
                await self.api.cancel(long_spec.symbol, self._orders["long"].order_id)
            raise
    
    async def _wait_till_trigger(self, leg_name: str, order_id: str, target_sz: int) -> None:
        """异步等待订单触发"""
        iteration = 0
        
        print(f"   🔍 [{leg_name}] 监控线程启动，orderId={order_id}")
        
        while not self._done.is_set():
            iteration += 1
            
            # 查询订单状态（直接抛出异常，不隐藏错误）
            order = await self.api.get_order(order_id)
            self._orders[leg_name] = order
            
            # 计算成交比例
            if target_sz > 0:
                fill_ratio = order.filled_sz / target_sz
            else:
                fill_ratio = 0.0
            
            # 显示进度（每3次显示一次，减少刷屏）
            if iteration % 3 == 1:
                fill_pct = fill_ratio * 100
                print(f"   📊 [{leg_name}] {fill_pct:.1f}% filled, status={order.status}")
            
            # 检查是否触发
            if order.status in ("filled", "partially_filled") and fill_ratio >= self.trigger_fill_ratio:
                async with self._lock:
                    if not self._winner:
                        self._winner = leg_name
                        self._done.set()
                        print(f"\n🎉 {leg_name.capitalize()}腿触发！({order.filled_sz}/{target_sz})")
                        break
            
            # 检查异常状态
            if order.status in ("canceled", "rejected"):
                print(f"\n⚠️ {leg_name.capitalize()}腿订单异常: {order.status}")
                break
            
            # 等待下次检查
            await asyncio.sleep(self.poll_interval)
    
    async def _cancel_and_aggress(self, winner: str, loser: str) -> Dict[str, Any]:
        """撤销输家订单并强制成交"""
        loser_order = self._orders[loser]
        loser_label = loser.capitalize()
        currency = loser_order.symbol.split("-")[0]
        
        print(f"\n{'='*70}")
        print(f"⚡ 收尾: 撤销{loser_label}腿 + 强制成交")
        print(f"{'='*70}")
        
        # 1. 撤单
        print(f"📋 撤销{loser_label}腿订单...")
        start_cancel = time.time()
        
        try:
            await asyncio.wait_for(
                self.api.cancel(loser_order.symbol, loser_order.order_id),
                timeout=self.cancel_timeout
            )
            cancel_time = time.time() - start_cancel
            print(f"   ✅ 撤单请求已发送 (耗时: {cancel_time:.2f}秒)")
        except asyncio.TimeoutError:
            print(f"   ⚠️ 撤单超时，继续处理...")
        except Exception as e:
            print(f"   ⚠️ 撤单异常: {e}")
        
        # 2. 等待撤单生效（增加等待时间以确保交易所处理完成）
        print(f"   ⏳ 等待撤单生效...")
        await asyncio.sleep(0.5)  # 从0.2秒增加到0.5秒
        
        # 3. 查询最新状态
        loser_order = await self.api.get_order(loser_order.order_id)
        self._orders[loser] = loser_order
        
        print(f"   📊 当前状态: {loser_order.status}, 已成交: {loser_order.filled_sz}/{loser_order.sz}")
        
        remain_sz = loser_order.sz - loser_order.filled_sz
        
        if remain_sz <= 0:
            print(f"   ℹ️ {loser_label}腿已完全成交，无需市价单")
            return {"success": True, "aggress": False}
        
        # 3. 激进成交剩余数量
        print(f"\n💥 激进成交剩余 {remain_sz} contracts")
        
        aggress_order = await self.api.place_aggressive(
            loser_order.symbol,
            loser_order.side,
            remain_sz,
            self.max_slippage_ticks
        )
        print(f"   ✅ 激进单已下达 (ordId: {aggress_order.order_id})")
        
        # 等待成交（最多等待3秒）
        print(f"   🔍 等待成交确认...")
        max_wait = 3.0
        check_interval = 0.3
        elapsed = 0.0
        
        while elapsed < max_wait:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            # 查询订单状态
            aggress_status = await self.api.get_order(aggress_order.order_id)
            
            if aggress_status.status == "filled":
                print(f"   ✅ 完全成交！({aggress_status.filled_sz}/{aggress_status.sz})")
                return {
                    "success": True, 
                    "aggress": True, 
                    "aggress_sz": remain_sz,
                    "filled_sz": aggress_status.filled_sz
                }
            elif aggress_status.status == "partially_filled":
                print(f"   ⏳ 部分成交 ({aggress_status.filled_sz}/{aggress_status.sz})")
                continue
            elif aggress_status.status in ("canceled", "rejected"):
                print(f"   ⚠️ 激进单异常: {aggress_status.status}")
                break
        
        # 超时或异常，查询最终状态
        final_status = await self.api.get_order(aggress_order.order_id)
        if final_status.filled_sz > 0:
            print(f"   ⚠️ 部分成交 ({final_status.filled_sz}/{final_status.sz})")
            return {
                "success": True, 
                "aggress": True, 
                "aggress_sz": remain_sz,
                "filled_sz": final_status.filled_sz,
                "partial": True
            }
        else:
            print(f"   ⚠️ 激进单未成交，使用对手盘价格强制成交")
            
            # 撤销未成交的激进单
            await self.api.cancel(loser_order.symbol, aggress_order.order_id)
            await asyncio.sleep(0.3)
            
            # 使用对手盘价格挂限价单强制成交
            loop = asyncio.get_event_loop()
            
            # 获取最新盘口
            orderbook = await loop.run_in_executor(
                None,
                self.api.client.get_orderbook,
                loser_order.symbol
            )
            
            if not orderbook:
                print(f"   ❌ 无法获取盘口，强制成交失败")
                return {"success": False, "error": "Failed to get orderbook"}
            
            # 根据方向选择对手盘价格
            if loser_order.side == "buy":
                # 买单：直接用ask价（卖一价）吃掉对手盘
                force_price = orderbook["ask"]
                price_desc = f"ask ({force_price:.4f})"
            else:
                # 卖单：直接用bid价（买一价）吃掉对手盘
                force_price = orderbook["bid"]
                price_desc = f"bid ({force_price:.4f})"
            
            print(f"   💥 强制成交价格: {force_price:.4f} ({price_desc})")
            
            force_result = await loop.run_in_executor(
                None,
                self.api.client.place_limit_order,
                loser_order.symbol, loser_order.side, remain_sz, force_price,
                False,  # post_only=False
                None    # cl_ord_id
            )
            
            if force_result.get("success"):
                print(f"   ✅ 强制成交单已执行 (ordId: {force_result['ordId']})")
                
                # 等待1秒确认成交
                await asyncio.sleep(1.0)
                force_order_id = force_result["ordId"]
                final_check = await self.api.get_order(force_order_id)
                
                print(f"   📊 最终状态: {final_check.status}, 已成交: {final_check.filled_sz}/{final_check.sz}")
                
                return {
                    "success": True,
                    "aggress": True,
                    "aggress_sz": remain_sz,
                    "filled_sz": final_check.filled_sz,
                    "force_order": True,
                    "force_price": force_price
                }
            else:
                print(f"   ❌ 强制成交失败: {force_result.get('error')}")
                return {"success": False, "error": "Force order failed"}
    
    async def execute(self) -> Dict[str, Any]:
        """执行完整的异步协同下单流程"""
        self.start_time = time.time()
        
        try:
            # 1. 挂出两腿
            short_order, long_order = await self._place_both_legs()
            
            # 2. 并发监控两腿（真正的并发！）
            print(f"\n🔍 启动异步监控（poll_interval={self.poll_interval}s）...")
            
            waiter_short = asyncio.create_task(
                self._wait_till_trigger("short", short_order.order_id, short_order.sz)
            )
            waiter_long = asyncio.create_task(
                self._wait_till_trigger("long", long_order.order_id, long_order.sz)
            )
            
            # 等待任一腿触发
            await self._done.wait()
            self.trigger_time = time.time()
            
            # 3. 确定输家
            async with self._lock:
                winner = self._winner
            
            if not winner:
                print("\n⚠️ 无触发腿，可能订单被取消")
                waiter_short.cancel()
                waiter_long.cancel()
                return {"success": False, "error": "No winner"}
            
            loser = "long" if winner == "short" else "short"
            
            # 4. 收尾
            result = await self._cancel_and_aggress(winner, loser)
            
            # 停止监控任务
            waiter_short.cancel()
            waiter_long.cancel()
            
            # 统计
            total_time = time.time() - self.start_time
            trigger_to_finish = time.time() - self.trigger_time
            
            print(f"\n{'='*70}")
            print(f"✅ 异步协同下单完成")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"⚡ 触发响应: {trigger_to_finish:.2f}秒")
            print(f"🏆 触发腿: {winner.upper()}")
            
            short_final = self._orders["short"]
            long_final = self._orders["long"]
            print(f"📊 Short: {short_final.filled_sz}/{short_final.sz} @ {short_final.avg_px:.4f}")
            print(f"📊 Long:  {long_final.filled_sz}/{long_final.sz} @ {long_final.avg_px:.4f}")
            
            return {
                "success": True,
                "winner": winner,
                "total_time": total_time,
                "trigger_to_finish": trigger_to_finish,
                "short_order": short_final,
                "long_order": long_final,
                "result": result
            }
            
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")
            
            # 清理：撤销所有订单
            cleanup_tasks = []
            if "short" in self._orders:
                cleanup_tasks.append(
                    self.api.cancel(
                        self._orders["short"].symbol,
                        self._orders["short"].order_id
                    )
                )
            if "long" in self._orders:
                cleanup_tasks.append(
                    self.api.cancel(
                        self._orders["long"].symbol,
                        self._orders["long"].order_id
                    )
                )
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            raise


def place_calendar_spread_async(
    opportunity: CalendarSpreadOpportunity,
    crypto_notional: float,
    simulated: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    便捷函数：执行异步Calendar Spread协同下单
    
    Args:
        opportunity: Calendar Spread机会
        crypto_notional: 交易数量（币本位）
        simulated: 是否模拟盘
        **kwargs: 传递给AsyncCalendarSpreadCoordinator的其他参数
    
    Returns:
        执行结果
    """
    client = OKXOptionsClient(simulated=simulated)
    coordinator = AsyncCalendarSpreadCoordinator(
        client, opportunity, crypto_notional, **kwargs
    )
    
    # 运行异步协程
    return asyncio.run(coordinator.execute())

