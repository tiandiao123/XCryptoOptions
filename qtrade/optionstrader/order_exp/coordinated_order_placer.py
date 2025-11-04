#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calendar Spread协同下单策略
实现两腿被动挂单+任一腿触发后另一腿强制成交的策略
"""

import time
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass

from qtrade.order_api.okx.client.options_client import OKXOptionsClient
from qtrade.optionstrader.arbitrage_searcher.option_data import CalendarSpreadOpportunity


@dataclass
class OrderStatus:
    """订单状态"""
    ord_id: str
    inst_id: str
    side: str
    sz: int
    filled_sz: int = 0
    avg_px: float = 0.0
    state: str = "live"  # live, partially_filled, filled, canceled


class CalendarSpreadCoordinator:
    """
    Calendar Spread协同下单器
    
    策略流程：
    1. 同时挂出两腿被动限价单（short sell + long buy）
    2. 轮询监控，任意一腿完全成交即触发
    3. 立即撤销另一腿，并用市价单强制成交
    
    优势：
    - 两腿都尽量以被动价成交，节省成本
    - 避免单腿暴露风险
    """
    
    def __init__(
        self,
        client: OKXOptionsClient,
        opportunity: CalendarSpreadOpportunity,
        crypto_notional: float,
        price_offset: float = 0.0001,  # 相对盘口的价格偏移
        poll_interval: float = 0.5,    # 轮询间隔（秒）
        cancel_timeout: float = 3.0,   # 撤单超时（秒）
        trigger_ratio: float = 1.0     # 触发比率（1.0=完全成交）
    ):
        """
        初始化Calendar Spread协调器
        
        Args:
            client: OKX期权客户端
            opportunity: Calendar Spread机会
            crypto_notional: 交易数量（币本位）
            price_offset: 价格偏移（正数表示改善价格）
            poll_interval: 轮询间隔
            cancel_timeout: 撤单超时
            trigger_ratio: 触发比率（0-1，1.0表示必须完全成交）
        """
        self.client = client
        self.opp = opportunity
        self.crypto_notional = crypto_notional
        self.price_offset = price_offset
        self.poll_interval = poll_interval
        self.cancel_timeout = cancel_timeout
        self.trigger_ratio = trigger_ratio
        
        # 订单跟踪
        self.short_order: Optional[OrderStatus] = None
        self.long_order: Optional[OrderStatus] = None
        self.winner: Optional[str] = None  # "short" or "long"
        
        # 统计
        self.start_time: float = 0
        self.trigger_time: float = 0
        
    def _get_passive_price(self, inst_id: str, side: str) -> float:
        """
        计算被动挂单价格（略优于当前盘口）
        
        Args:
            inst_id: 期权合约ID
            side: "buy" or "sell"
        
        Returns:
            挂单价格
        """
        book = self.client.get_orderbook(inst_id)
        if not book:
            raise RuntimeError(f"Cannot get orderbook for {inst_id}")
        
        if side == "sell":
            # 卖单：略低于ask，提高成交概率
            price = book["ask"] - self.price_offset
        else:
            # 买单：略高于bid
            price = book["bid"] + self.price_offset
        
        # 确保价格在bid-ask之间
        price = max(book["bid"], min(price, book["ask"]))
        
        return round(price, 4)
    
    def _place_both_legs(self) -> Tuple[str, str]:
        """
        同时挂出两腿被动限价单
        
        Returns:
            (short_ord_id, long_ord_id)
        """
        currency = self.opp.short_option.symbol.split("-")[0]
        
        print(f"\n{'='*70}")
        print(f"🎯 [Calendar Spread] 开始协同下单")
        print(f"{'='*70}")
        print(f"📊 交易对:")
        print(f"   Short (卖出): {self.opp.short_option.symbol}")
        print(f"   Long (买入):  {self.opp.long_option.symbol}")
        print(f"   数量: {self.crypto_notional} {currency}")
        print(f"   策略: 被动挂单 + 触发跟随")
        
        # 计算两腿的sz
        short_sz = self.client._contracts_from_crypto_notional(
            self.opp.short_option.symbol, 
            self.crypto_notional
        )
        long_sz = self.client._contracts_from_crypto_notional(
            self.opp.long_option.symbol, 
            self.crypto_notional
        )
        
        # 计算挂单价格
        short_px = self._get_passive_price(self.opp.short_option.symbol, "sell")
        long_px = self._get_passive_price(self.opp.long_option.symbol, "buy")
        
        print(f"\n📝 挂单价格:")
        print(f"   Short: {short_px:.4f} {currency} (sz={short_sz})")
        print(f"   Long:  {long_px:.4f} {currency} (sz={long_sz})")
        
        # 挂出两腿订单
        print(f"\n📤 挂出Short腿...")
        short_result = self.client.place_limit_order(
            inst_id=self.opp.short_option.symbol,
            side="sell",
            sz=short_sz,
            px=short_px
        )
        
        if not short_result.get("success"):
            raise RuntimeError(f"Short leg order failed: {short_result.get('error')}")
        
        short_ord_id = short_result["ordId"]
        self.short_order = OrderStatus(
            ord_id=short_ord_id,
            inst_id=self.opp.short_option.symbol,
            side="sell",
            sz=short_sz
        )
        print(f"   ✅ Short订单已挂出: {short_ord_id}")
        
        print(f"\n📤 挂出Long腿...")
        long_result = self.client.place_limit_order(
            inst_id=self.opp.long_option.symbol,
            side="buy",
            sz=long_sz,
            px=long_px
        )
        
        if not long_result.get("success"):
            # Short已挂出，需要撤销
            print(f"   ⚠️ Long腿挂单失败，撤销Short腿...")
            self.client.cancel_order(self.opp.short_option.symbol, ord_id=short_ord_id)
            raise RuntimeError(f"Long leg order failed: {long_result.get('error')}")
        
        long_ord_id = long_result["ordId"]
        self.long_order = OrderStatus(
            ord_id=long_ord_id,
            inst_id=self.opp.long_option.symbol,
            side="buy",
            sz=long_sz
        )
        print(f"   ✅ Long订单已挂出: {long_ord_id}")
        
        print(f"\n✅ 两腿订单挂出完成，开始监控...")
        
        return short_ord_id, long_ord_id
    
    def _get_order_status(self, ord_id: str) -> OrderStatus:
        """
        获取订单状态
        
        Args:
            ord_id: 订单ID
        
        Returns:
            订单状态
        """
        order_info = self.client.get_order_info(ord_id)
        
        if not order_info:
            # 保持当前状态
            if self.short_order and self.short_order.ord_id == ord_id:
                return self.short_order
            else:
                return self.long_order
        
        return OrderStatus(
            ord_id=order_info["ordId"],
            inst_id=order_info["instId"],
            side=order_info["side"],
            sz=int(order_info["sz"]),
            filled_sz=int(float(order_info.get("accFillSz", 0))),
            avg_px=float(order_info.get("avgPx", 0)),
            state=order_info["state"]
        )
    
    def _check_trigger(self, order: OrderStatus) -> bool:
        """
        检查订单是否触发
        
        Args:
            order: 订单状态
        
        Returns:
            是否触发
        """
        if order.sz == 0:
            return False
        
        fill_ratio = order.filled_sz / order.sz
        
        # 检查状态和成交比例
        if order.state in ("filled", "partially_filled") and fill_ratio >= self.trigger_ratio:
            return True
        
        return False
    
    def _monitor_until_trigger(self) -> str:
        """
        监控两腿订单直到任一触发
        
        Returns:
            触发的腿 ("short" or "long")
        """
        print(f"\n🔍 监控订单状态（轮询间隔: {self.poll_interval}秒）...")
        
        iteration = 0
        while True:
            iteration += 1
            
            # 更新订单状态
            self.short_order = self._get_order_status(self.short_order.ord_id)
            self.long_order = self._get_order_status(self.long_order.ord_id)
            
            # 显示进度（每10次轮询显示一次）
            if iteration % 10 == 1:
                short_fill_pct = (self.short_order.filled_sz / self.short_order.sz * 100) if self.short_order.sz > 0 else 0
                long_fill_pct = (self.long_order.filled_sz / self.long_order.sz * 100) if self.long_order.sz > 0 else 0
                print(f"   📊 Short: {short_fill_pct:.1f}% | Long: {long_fill_pct:.1f}%")
            
            # 检查Short腿
            if self._check_trigger(self.short_order):
                print(f"\n🎉 Short腿触发！(成交: {self.short_order.filled_sz}/{self.short_order.sz})")
                return "short"
            
            # 检查Long腿
            if self._check_trigger(self.long_order):
                print(f"\n🎉 Long腿触发！(成交: {self.long_order.filled_sz}/{self.long_order.sz})")
                return "long"
            
            # 检查订单是否被取消/拒绝
            if self.short_order.state in ("canceled", "rejected"):
                print(f"\n⚠️ Short腿订单异常: {self.short_order.state}")
                # 撤销Long腿
                self.client.cancel_order(self.long_order.inst_id, ord_id=self.long_order.ord_id)
                raise RuntimeError(f"Short leg order {self.short_order.state}")
            
            if self.long_order.state in ("canceled", "rejected"):
                print(f"\n⚠️ Long腿订单异常: {self.long_order.state}")
                # 撤销Short腿
                self.client.cancel_order(self.short_order.inst_id, ord_id=self.short_order.ord_id)
                raise RuntimeError(f"Long leg order {self.long_order.state}")
            
            # 等待下次轮询
            time.sleep(self.poll_interval)
    
    def _cancel_and_aggress(self, winner: str) -> Dict[str, Any]:
        """
        撤销输家订单并用市价单强制成交
        
        Args:
            winner: 赢家腿 ("short" or "long")
        
        Returns:
            执行结果
        """
        if winner == "short":
            loser_order = self.long_order
            loser_label = "Long"
        else:
            loser_order = self.short_order
            loser_label = "Short"
        
        currency = loser_order.inst_id.split("-")[0]
        
        print(f"\n{'='*70}")
        print(f"⚡ 开始收尾: 撤销{loser_label}腿 + 市价成交")
        print(f"{'='*70}")
        
        # 1. 撤销输家订单
        print(f"📋 撤销{loser_label}腿订单...")
        start_cancel = time.time()
        
        try:
            cancel_result = self.client.cancel_order(
                loser_order.inst_id, 
                ord_id=loser_order.ord_id
            )
            cancel_time = time.time() - start_cancel
            print(f"   ✅ 撤单完成 (耗时: {cancel_time:.2f}秒)")
        except Exception as e:
            print(f"   ⚠️ 撤单异常: {e}")
            # 继续执行，可能订单已成交
        
        # 2. 查询剩余数量
        time.sleep(0.2)  # 等待撤单生效
        loser_order = self._get_order_status(loser_order.ord_id)
        remain_sz = loser_order.sz - loser_order.filled_sz
        
        if remain_sz <= 0:
            print(f"   ℹ️ {loser_label}腿已完全成交，无需市价单")
            return {"success": True, "aggress": False, "filled_sz": loser_order.filled_sz}
        
        # 3. 用市价单强制成交剩余数量
        print(f"\n💥 市价成交{loser_label}腿剩余数量: {remain_sz} contracts")
        
        aggress_result = self.client.place_market_order(
            inst_id=loser_order.inst_id,
            side=loser_order.side,
            sz=remain_sz
        )
        
        if aggress_result.get("success"):
            print(f"   ✅ 市价单已提交: {aggress_result.get('ordId')}")
            return {
                "success": True,
                "aggress": True,
                "filled_sz": loser_order.filled_sz,
                "aggress_sz": remain_sz,
                "aggress_ord_id": aggress_result.get("ordId")
            }
        else:
            print(f"   ❌ 市价单失败: {aggress_result.get('error')}")
            return {
                "success": False,
                "error": aggress_result.get("error")
            }
    
    def execute(self) -> Dict[str, Any]:
        """
        执行完整的Calendar Spread协同下单流程
        
        Returns:
            执行结果
        """
        self.start_time = time.time()
        
        try:
            # 1. 挂出两腿
            self._place_both_legs()
            
            # 2. 监控直到触发
            self.winner = self._monitor_until_trigger()
            self.trigger_time = time.time()
            
            # 3. 收尾
            result = self._cancel_and_aggress(self.winner)
            
            total_time = time.time() - self.start_time
            trigger_to_finish = time.time() - self.trigger_time
            
            print(f"\n{'='*70}")
            print(f"✅ Calendar Spread协同下单完成")
            print(f"{'='*70}")
            print(f"⏱️  总耗时: {total_time:.2f}秒")
            print(f"⚡ 触发后处理: {trigger_to_finish:.2f}秒")
            print(f"🏆 触发腿: {self.winner.upper()}")
            print(f"📊 Short腿: {self.short_order.filled_sz}/{self.short_order.sz} @ {self.short_order.avg_px:.4f}")
            print(f"📊 Long腿:  {self.long_order.filled_sz}/{self.long_order.sz} @ {self.long_order.avg_px:.4f}")
            
            return {
                "success": True,
                "winner": self.winner,
                "total_time": total_time,
                "trigger_to_finish": trigger_to_finish,
                "short_order": self.short_order,
                "long_order": self.long_order,
                "result": result
            }
            
        except Exception as e:
            print(f"\n❌ 执行失败: {e}")
            
            # 尝试清理：撤销所有挂单
            if self.short_order:
                try:
                    self.client.cancel_order(self.short_order.inst_id, ord_id=self.short_order.ord_id)
                except:
                    pass
            
            if self.long_order:
                try:
                    self.client.cancel_order(self.long_order.inst_id, ord_id=self.long_order.ord_id)
                except:
                    pass
            
            raise


def place_calendar_spread_coordinated(
    opportunity: CalendarSpreadOpportunity,
    crypto_notional: float,
    simulated: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    便捷函数：执行Calendar Spread协同下单
    
    Args:
        opportunity: Calendar Spread机会
        crypto_notional: 交易数量（币本位）
        simulated: 是否模拟盘
        **kwargs: 传递给CalendarSpreadCoordinator的其他参数
    
    Returns:
        执行结果
    """
    client = OKXOptionsClient(simulated=simulated)
    coordinator = CalendarSpreadCoordinator(client, opportunity, crypto_notional, **kwargs)
    return coordinator.execute()

