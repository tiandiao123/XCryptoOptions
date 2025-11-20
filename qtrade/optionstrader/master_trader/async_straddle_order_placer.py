#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Straddle 异步协同下单策略
使用asyncio实现真正的并发监控和快速响应

核心特性：
1. 开仓：Call卖 + Put卖（双卖）
2. 平仓：Call买 + Put买（双买）
3. 异步监控：0.3秒轮询，任一腿成交立即响应
4. 智能收尾：撤单 + Aggressive成交另一腿
"""

import asyncio
import time
from typing import Dict, Any, Optional, Tuple

from qtrade.optionstrader.master_trader.async_calendar_order_placer import (
    OKXAsyncAPI,
    OrderSpec,
    ActiveOrder
)
from qtrade.order_api.okx.client.options_client import OKXOptionsClient
from qtrade.optionstrader.arbitrage_searcher.option_data import StraddleOpportunityOKX


class AsyncStraddleCoordinator:
    """
    异步 Straddle 协同下单器
    
    核心特性：
    1. 开仓：Call卖 + Put卖（双卖策略）
    2. 平仓：Call买 + Put买（双买平仓）
    3. 使用asyncio并发监控两腿订单
    4. 任一腿触发立即响应（无轮询延迟）
    5. 快速撤单和市价成交
    """
    
    def __init__(
        self,
        client: OKXOptionsClient,
        opportunity: StraddleOpportunityOKX,
        crypto_notional: float,
        price_offset_ticks: int = 1,
        trigger_fill_ratio: float = 1.0,
        max_slippage_ticks: int = 2,
        cancel_timeout: float = 3.0,
        poll_interval: float = 0.3
    ):
        """
        初始化异步 Straddle 协调器
        
        Args:
            client: OKX期权客户端
            opportunity: Straddle机会
            crypto_notional: 交易数量（币本位）
            price_offset_ticks: 价格偏移（tick数量）
            trigger_fill_ratio: 触发比率（0-1）
            max_slippage_ticks: 最大滑点（tick数量）
            cancel_timeout: 撤单超时
            poll_interval: 轮询间隔
        """
        self.api = OKXAsyncAPI(client)
        self.straddle = opportunity
        self.crypto_notional = crypto_notional
        self.price_offset_ticks = price_offset_ticks
        self.trigger_fill_ratio = trigger_fill_ratio
        self.max_slippage_ticks = max_slippage_ticks
        self.cancel_timeout = cancel_timeout
        self.poll_interval = poll_interval
        
        # 状态跟踪
        self._done = asyncio.Event()
        self._lock = asyncio.Lock()
        self._winner: Optional[str] = None  # "call" or "put"
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
        """
        Straddle 开仓 - 双卖
        
        Call 卖 + Put 卖
        """
        currency = self.straddle.call_option.symbol.split("-")[0]
        
        print(f"\n{'='*70}")
        print(f"🎯 [Async Straddle] 开始协同下单")
        print(f"{'='*70}")
        print(f"📊 交易对:")
        print(f"   Call (卖出): {self.straddle.call_option.symbol}")
        print(f"   Put (卖出):  {self.straddle.put_option.symbol}")
        print(f"   数量: {self.crypto_notional} {currency}")
        print(f"   策略: Short Straddle (双卖)")
        
        # Straddle 开仓：两腿都是卖
        call_spec = OrderSpec(
            symbol=self.straddle.call_option.symbol,
            side="sell",
            crypto_notional=self.crypto_notional,
            price_offset_ticks=self.price_offset_ticks
        )
        
        put_spec = OrderSpec(
            symbol=self.straddle.put_option.symbol,
            side="sell",
            crypto_notional=self.crypto_notional,
            price_offset_ticks=self.price_offset_ticks
        )
        
        # 计算sz和价格
        call_sz = self.api.client._contracts_from_crypto_notional(
            call_spec.symbol,
            call_spec.crypto_notional
        )
        put_sz = self.api.client._contracts_from_crypto_notional(
            put_spec.symbol,
            put_spec.crypto_notional
        )
        
        call_px = await self._price_for_passive(call_spec)
        put_px = await self._price_for_passive(put_spec)
        
        print(f"\n📝 挂单价格:")
        print(f"   Call: {call_px:.4f} {currency} (sz={call_sz})")
        print(f"   Put:  {put_px:.4f} {currency} (sz={put_sz})")
        
        # 并发挂出两腿
        print(f"\n📤 并发挂出两腿订单...")
        
        try:
            call_order, put_order = await asyncio.gather(
                self.api.place_limit(call_spec.symbol, "sell", call_sz, call_px),
                self.api.place_limit(put_spec.symbol, "sell", put_sz, put_px)
            )
            
            self._orders["call"] = call_order
            self._orders["put"] = put_order
            
            print(f"   ✅ Call订单: {call_order.order_id}")
            print(f"   ✅ Put订单: {put_order.order_id}")
            print(f"✅ 两腿挂单完成，开始异步监控...")
            
            return call_order, put_order
            
        except Exception as e:
            print(f"❌ 挂单失败: {e}")
            if "call" in self._orders:
                await self.api.cancel(call_spec.symbol, self._orders["call"].order_id)
            if "put" in self._orders:
                await self.api.cancel(put_spec.symbol, self._orders["put"].order_id)
            raise
    
    async def _wait_till_trigger(self, leg_name: str, order_id: str, target_sz: int) -> None:
        """异步等待订单触发"""
        iteration = 0
        
        print(f"   🔍 [{leg_name}] 监控线程启动，orderId={order_id}")
        
        while not self._done.is_set():
            iteration += 1
            
            # 查询订单状态
            order = await self.api.get_order(order_id)
            self._orders[leg_name] = order
            
            # 计算成交比例
            if target_sz > 0:
                fill_ratio = order.filled_sz / target_sz
            else:
                fill_ratio = 0.0
            
            # 显示进度（每3次显示一次）
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
        
        # 2. 等待撤单生效
        print(f"   ⏳ 等待撤单生效...")
        await asyncio.sleep(0.5)
        
        # 3. 查询最新状态
        loser_order = await self.api.get_order(loser_order.order_id)
        self._orders[loser] = loser_order
        
        print(f"   📊 当前状态: {loser_order.status}, 已成交: {loser_order.filled_sz}/{loser_order.sz}")
        
        remain_sz = loser_order.sz - loser_order.filled_sz
        
        if remain_sz <= 0:
            print(f"   ℹ️ {loser_label}腿已完全成交，无需市价单")
            return {"success": True, "aggress": False}
        
        # 4. 激进成交剩余数量
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
        
        print(f"   ⚠️ 激进单未成交")
        return {"success": False, "error": "Aggressive order not filled"}
    
    async def execute(self) -> Dict[str, Any]:
        """执行完整的异步协同下单流程（开仓）"""
        self.start_time = time.time()
        
        try:
            # 1. 挂出两腿
            call_order, put_order = await self._place_both_legs()
            
            # 2. 并发监控两腿
            print(f"\n🔍 启动异步监控（poll_interval={self.poll_interval}s）...")
            
            waiter_call = asyncio.create_task(
                self._wait_till_trigger("call", call_order.order_id, call_order.sz)
            )
            waiter_put = asyncio.create_task(
                self._wait_till_trigger("put", put_order.order_id, put_order.sz)
            )
            
            # 等待任一腿触发
            await self._done.wait()
            self.trigger_time = time.time()
            
            # 3. 确定输家
            async with self._lock:
                winner = self._winner
            
            if not winner:
                print("\n⚠️ 无触发腿，可能订单被取消")
                waiter_call.cancel()
                waiter_put.cancel()
                return {"success": False, "error": "No winner"}
            
            loser = "put" if winner == "call" else "call"
            
            # 4. 收尾
            result = await self._cancel_and_aggress(winner, loser)
            
            # 停止监控任务
            waiter_call.cancel()
            waiter_put.cancel()
            
            # 统计
            total_time = time.time() - self.start_time
            trigger_to_finish = time.time() - self.trigger_time
            
            print(f"\n{'='*70}")
            print(f"✅ 异步协同下单完成")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"⚡ 触发响应: {trigger_to_finish:.2f}秒")
            print(f"🏆 触发腿: {winner.upper()}")
            
            call_final = self._orders["call"]
            put_final = self._orders["put"]
            print(f"📊 Call: {call_final.filled_sz}/{call_final.sz} @ {call_final.avg_px:.4f}")
            print(f"📊 Put:  {put_final.filled_sz}/{put_final.sz} @ {put_final.avg_px:.4f}")
            
            return {
                "success": True,
                "winner": winner,
                "total_time": total_time,
                "trigger_to_finish": trigger_to_finish,
                "call_order": call_final,
                "put_order": put_final,
                "result": result
            }
            
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")
            
            # 清理：撤销所有订单
            cleanup_tasks = []
            if "call" in self._orders:
                cleanup_tasks.append(
                    self.api.cancel(
                        self._orders["call"].symbol,
                        self._orders["call"].order_id
                    )
                )
            if "put" in self._orders:
                cleanup_tasks.append(
                    self.api.cancel(
                        self._orders["put"].symbol,
                        self._orders["put"].order_id
                    )
                )
            
            if cleanup_tasks:
                await asyncio.gather(*cleanup_tasks, return_exceptions=True)
            
            raise
    
    async def close(self, aggressive: bool = False) -> Dict[str, Any]:
        """
        Straddle 平仓 - 双买
        
        Call 买 + Put 买
        
        Args:
            aggressive: 是否激进平仓
                - True: 直接对手方价格成交（快速）
                - False: 挂限价单等待，任意一腿成交后另一腿aggressive成交（省成本）
        
        Returns:
            执行结果
        """
        self.start_time = time.time()
        
        try:
            # 计算平仓数量
            call_sz = self.api.client._contracts_from_crypto_notional(
                self.straddle.call_option.symbol,
                self.crypto_notional
            )
            put_sz = self.api.client._contracts_from_crypto_notional(
                self.straddle.put_option.symbol,
                self.crypto_notional
            )
            
            print(f"\n{'='*70}")
            print(f"🔻 异步协同平仓 Straddle")
            print(f"{'='*70}")
            print(f"   Call (买回): {self.straddle.call_option.symbol} × {call_sz} 张")
            print(f"   Put (买回):  {self.straddle.put_option.symbol} × {put_sz} 张")
            print(f"   模式: {'激进' if aggressive else '保守'}")
            
            if aggressive:
                # 激进模式：直接对手方价格成交
                print(f"\n💥 激进平仓：并发对手方价格成交...")
                
                call_order, put_order = await asyncio.gather(
                    self.api.place_aggressive(
                        self.straddle.call_option.symbol, "buy", call_sz, 2
                    ),
                    self.api.place_aggressive(
                        self.straddle.put_option.symbol, "buy", put_sz, 2
                    )
                )
                
                print(f"   ✅ Call平仓: {call_order.order_id}")
                print(f"   ✅ Put平仓: {put_order.order_id}")
                
                await asyncio.sleep(2)
                
                call_final, put_final = await asyncio.gather(
                    self.api.get_order(call_order.order_id),
                    self.api.get_order(put_order.order_id)
                )
                
            else:
                # 保守模式：挂限价单，任意一腿成交后另一腿aggressive成交
                print(f"\n🎯 保守平仓：挂限价单等待成交...")
                
                # 重置事件
                self._done.clear()
                self._winner = None
                
                # 获取盘口
                loop = asyncio.get_event_loop()
                call_ob_task = loop.run_in_executor(
                    None, self.api.client.get_orderbook,
                    self.straddle.call_option.symbol
                )
                put_ob_task = loop.run_in_executor(
                    None, self.api.client.get_orderbook,
                    self.straddle.put_option.symbol
                )
                call_inst_task = loop.run_in_executor(
                    None, self.api.client.get_instrument_info,
                    self.straddle.call_option.symbol
                )
                put_inst_task = loop.run_in_executor(
                    None, self.api.client.get_instrument_info,
                    self.straddle.put_option.symbol
                )
                
                call_ob, put_ob, call_inst, put_inst = await asyncio.gather(
                    call_ob_task, put_ob_task, call_inst_task, put_inst_task
                )
                
                call_tick = float(call_inst.get("tickSz", 0.0001))
                put_tick = float(put_inst.get("tickSz", 0.0001))
                
                # 计算挂单价格（买回 → ask-1）
                call_price = call_ob["ask"] - call_tick
                put_price = put_ob["ask"] - put_tick
                
                print(f"   📝 Call买回: {call_price:.4f} (ask-1)")
                print(f"   📝 Put买回: {put_price:.4f} (ask-1)")
                
                # 挂单
                call_order, put_order = await asyncio.gather(
                    self.api.place_limit(
                        self.straddle.call_option.symbol, "buy", call_sz, call_price
                    ),
                    self.api.place_limit(
                        self.straddle.put_option.symbol, "buy", put_sz, put_price
                    )
                )
                
                self._orders["call"] = call_order
                self._orders["put"] = put_order
                
                print(f"   ✅ Call挂单: {call_order.order_id}")
                print(f"   ✅ Put挂单: {put_order.order_id}")
                
                # 异步监控
                print(f"\n🔍 启动异步监控（poll_interval={self.poll_interval}s）...")
                
                waiter_call = asyncio.create_task(
                    self._wait_till_trigger("call", call_order.order_id, call_sz)
                )
                waiter_put = asyncio.create_task(
                    self._wait_till_trigger("put", put_order.order_id, put_sz)
                )
                
                # 等待任一腿触发
                await self._done.wait()
                self.trigger_time = time.time()
                
                # 确定赢家输家
                async with self._lock:
                    winner = self._winner
                
                if not winner:
                    print("\n⚠️ 无触发腿，可能订单被取消")
                    waiter_call.cancel()
                    waiter_put.cancel()
                    return {"success": False, "error": "No winner"}
                
                loser = "put" if winner == "call" else "call"
                
                # 收尾：撤单 + aggressive成交
                await self._cancel_and_aggress(winner, loser)
                
                # 清理任务
                waiter_call.cancel()
                waiter_put.cancel()
                
                call_final = self._orders["call"]
                put_final = self._orders["put"]
            
            total_time = time.time() - self.start_time
            
            print(f"\n{'='*70}")
            print(f"✅ 平仓完成")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"📊 Call: {call_final.filled_sz}/{call_sz} @ {call_final.avg_px:.4f}")
            print(f"📊 Put:  {put_final.filled_sz}/{put_sz} @ {put_final.avg_px:.4f}")
            print(f"{'='*70}\n")
            
            return {
                "success": True,
                "total_time": total_time,
                "call_close": call_final,
                "put_close": put_final
            }
            
        except Exception as e:
            print(f"\n❌ 平仓失败: {e}")
            return {"success": False, "error": str(e)}


# ============================================================================
# 便捷函数
# ============================================================================

def place_straddle_async(
    opportunity: StraddleOpportunityOKX,
    crypto_notional: float,
    simulated: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    便捷函数：执行异步 Straddle 协同下单
    
    Args:
        opportunity: Straddle 机会
        crypto_notional: 交易数量（币本位）
        simulated: 是否模拟盘
        **kwargs: 传递给 AsyncStraddleCoordinator 的其他参数
    
    Returns:
        执行结果
    """
    client = OKXOptionsClient(simulated=simulated)
    coordinator = AsyncStraddleCoordinator(
        client, opportunity, crypto_notional, **kwargs
    )
    
    # 运行异步协程
    return asyncio.run(coordinator.execute())


def close_straddle_async(
    opportunity: StraddleOpportunityOKX,
    crypto_notional: float,
    simulated: bool = True,
    aggressive: bool = False
) -> Dict[str, Any]:
    """
    便捷函数：异步平仓 Straddle 持仓
    
    策略：
    - aggressive=True: 直接对手方价格成交（快速）
    - aggressive=False: 挂限价单，任意一腿成交后另一腿aggressive成交（降低滑点，默认）
    
    Args:
        opportunity: Straddle 持仓信息
        crypto_notional: 平仓数量（币本位）
        simulated: 是否模拟盘
        aggressive: 是否激进平仓（默认False=保守模式）
    
    Returns:
        执行结果
    """
    client = OKXOptionsClient(simulated=simulated)
    coordinator = AsyncStraddleCoordinator(
        client, opportunity, crypto_notional
    )
    
    # 运行异步协程
    return asyncio.run(coordinator.close(aggressive=aggressive))

