#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Inverse Perpetual Contract 异步下单器

核心功能：
1. Long：在 ask-1 挂限价单
2. Short：在 bid+1 挂限价单
3. 等待指定时间（如30秒、1分钟）
4. 超时则撤单，改用 market order 成交
"""

import asyncio
import time
from typing import Dict, Any, Literal
from dataclasses import dataclass

from qtrade.order_api.okx.client.inverse_perp_client import OKXInversePerpClient
from qtrade.order_api.okx import API_KEY, API_SECRET, API_PASSPHRASE


Side = Literal["long", "short"]


@dataclass
class PerpOrder:
    """Perpetual 订单状态"""
    order_id: str
    inst_id: str
    side: str
    price: float
    sz: float
    filled_sz: float = 0.0
    avg_px: float = 0.0
    status: str = "live"  # live/partially_filled/filled/canceled


class AsyncInversePerpPlacer:
    """
    异步 Inverse Perpetual Contract 下单器
    
    策略：
    1. 优先挂限价单（ask-1 或 bid+1）
    2. 等待指定时间（wait_time）
    3. 超时则撤单改用 market order
    """
    
    def __init__(
        self,
        inst_id: str,
        side: Side,
        crypto_notional: float,
        simulated: bool = False,
        wait_time: float = 30.0,
        poll_interval: float = 0.5
    ):
        """
        初始化 Inverse Perp 下单器
        
        Args:
            inst_id: 合约标识（如 "ETH-USD-SWAP"）
            side: 方向 "long" 或 "short"
            crypto_notional: 交易数量（币本位）
            simulated: 是否模拟盘
            wait_time: 等待时间（秒），超时则改用 market order
            poll_interval: 轮询间隔（秒）
        """
        self.inst_id = inst_id
        self.side = side
        self.crypto_notional = crypto_notional
        self.simulated = simulated
        self.wait_time = wait_time
        self.poll_interval = poll_interval
        
        # 初始化客户端
        self.client = OKXInversePerpClient(
            api_key=API_KEY,
            api_secret=API_SECRET,
            passphrase=API_PASSPHRASE
        )
        
        # 状态
        self.order: PerpOrder = None
        self.start_time: float = 0
    
    def _get_orderbook(self) -> Dict[str, Any]:
        """获取盘口数据"""
        import requests
        
        url = "https://www.okx.com/api/v5/market/books"
        params = {"instId": self.inst_id, "sz": "1"}
        
        resp = requests.get(url, params=params, timeout=5)
        result = resp.json()
        
        if not result or result.get("code") != "0" or not result.get("data"):
            raise RuntimeError(f"无法获取盘口数据: {self.inst_id}")
        
        book = result["data"][0]
        bids = book.get("bids", [])
        asks = book.get("asks", [])
        
        if not bids or not asks:
            raise RuntimeError(f"盘口数据不完整: {self.inst_id}")
        
        return {
            "bid": float(bids[0][0]),
            "ask": float(asks[0][0]),
            "bid_sz": float(bids[0][1]),
            "ask_sz": float(asks[0][1])
        }
    
    def _get_tick_size(self) -> float:
        """获取 tick size"""
        inst_info = self.client.get_instrument_info(self.inst_id)
        return float(inst_info.get("tickSz", 0.1))
    
    def _calculate_limit_price(self, orderbook: Dict[str, Any], tick_sz: float) -> float:
        """
        计算限价单价格
        
        Long: ask - 1 tick (买入，挂在卖盘下方)
        Short: bid + 1 tick (卖出，挂在买盘上方)
        """
        if self.side == "long":
            # Long: 在 ask-1 挂单
            price = orderbook["ask"] - tick_sz
            print(f"   📝 Long 挂单价格: {price:.2f} (ask-1tick, ask={orderbook['ask']:.2f})")
        else:  # short
            # Short: 在 bid+1 挂单
            price = orderbook["bid"] + tick_sz
            print(f"   📝 Short 挂单价格: {price:.2f} (bid+1tick, bid={orderbook['bid']:.2f})")
        
        return price
    
    def _place_limit_order(self, price: float) -> str:
        """下限价单"""
        # OKX Perp 的方向：long=buy, short=sell
        okx_side = "buy" if self.side == "long" else "sell"
        
        # 使用 crypto_notional 下单（OKXInversePerpClient 会自动转换为合约张数）
        result = self.client.place_limit_order_crypto_notional(
            inst_id=self.inst_id,
            side=okx_side,
            crypto_notional=self.crypto_notional,
            px=price,
            td_mode="cross",
            reduce_only=False
        )
        
        # 检查返回码
        if result.get("code") != "0":
            error_msg = result.get("msg", "Unknown error")
            data = result.get("data", [])
            if data:
                error_msg = data[0].get("sMsg", error_msg)
            raise RuntimeError(f"限价单下单失败: {error_msg}")
        
        # 提取订单ID
        order_id = self.client._ord_id_or_raise(result)
        
        # 获取合约数量
        contracts = result.get("conversion_info", {}).get("contracts", 0)
        
        self.order = PerpOrder(
            order_id=order_id,
            inst_id=self.inst_id,
            side=okx_side,
            price=price,
            sz=float(contracts),
            status="live"
        )
        
        return order_id
    
    def _place_market_order(self, sz: float) -> str:
        """下市价单（使用剩余的币本位数量）"""
        okx_side = "buy" if self.side == "long" else "sell"
        
        # 计算剩余的币本位数量
        if self.order and self.order.sz > 0:
            # 根据已成交的合约数量计算剩余的币本位
            filled_contracts = self.order.filled_sz
            remain_ratio = (self.order.sz - filled_contracts) / self.order.sz
            remain_crypto = self.crypto_notional * remain_ratio
        else:
            remain_crypto = self.crypto_notional
        
        result = self.client.place_market_order_crypto_notional(
            inst_id=self.inst_id,
            side=okx_side,
            crypto_notional=remain_crypto,
            td_mode="cross",
            reduce_only=False
        )
        
        # 检查返回码
        if result.get("code") != "0":
            error_msg = result.get("msg", "Unknown error")
            data = result.get("data", [])
            if data:
                error_msg = data[0].get("sMsg", error_msg)
            raise RuntimeError(f"市价单下单失败: {error_msg}")
        
        return self.client._ord_id_or_raise(result)
    
    def _get_order_status(self, order_id: str) -> PerpOrder:
        """查询订单状态"""
        result = self.client.get_order_details(self.inst_id, order_id)
        
        if not result:
            return self.order  # 返回缓存状态
        
        return PerpOrder(
            order_id=result["ordId"],
            inst_id=result["instId"],
            side=result["side"],
            price=float(result.get("px", 0) or 0),
            sz=float(result.get("sz", 0) or 0),
            filled_sz=float(result.get("accFillSz", 0) or 0),
            avg_px=float(result.get("avgPx", 0) or 0),
            status=result["state"]
        )
    
    def _cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        try:
            result = self.client.cancel_order(self.inst_id, order_id)
            # 检查撤单是否成功
            code = result.get("code")
            if code == "0":
                return True
            else:
                print(f"   ⚠️ 撤单失败: code={code}, msg={result.get('msg')}")
                return False
        except Exception as e:
            print(f"   ⚠️ 撤单异常: {e}")
            return False
    
    async def execute(self) -> Dict[str, Any]:
        """
        执行异步下单流程
        
        Returns:
            {
                "success": bool,
                "order_id": str,
                "filled_sz": float,
                "avg_px": float,
                "execution_type": "limit" or "market",
                "total_time": float
            }
        """
        self.start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"🎯 [Async Inverse Perp] 开始下单")
        print(f"{'='*70}")
        print(f"   合约: {self.inst_id}")
        print(f"   方向: {self.side.upper()}")
        print(f"   数量: {self.crypto_notional} 币")
        print(f"   等待时间: {self.wait_time}秒")
        print(f"   模式: {'🧪 模拟盘' if self.simulated else '🔴 实盘'}")
        
        try:
            # 1. 获取盘口和 tick size
            print(f"\n📊 获取盘口信息...")
            loop = asyncio.get_event_loop()
            orderbook = await loop.run_in_executor(None, self._get_orderbook)
            tick_sz = await loop.run_in_executor(None, self._get_tick_size)
            
            print(f"   Bid: {orderbook['bid']:.2f} (size: {orderbook['bid_sz']:.0f})")
            print(f"   Ask: {orderbook['ask']:.2f} (size: {orderbook['ask_sz']:.0f})")
            print(f"   Tick: {tick_sz}")
            
            # 2. 计算限价单价格
            limit_price = self._calculate_limit_price(orderbook, tick_sz)
            
            # 3. 下限价单
            print(f"\n📤 下限价单...")
            order_id = await loop.run_in_executor(
                None, self._place_limit_order, limit_price
            )
            print(f"   ✅ 订单已提交: {order_id}")
            
            # 4. 等待成交（带超时）
            print(f"\n⏳ 等待成交（最多 {self.wait_time}秒）...")
            elapsed = 0.0
            check_count = 0
            
            while elapsed < self.wait_time:
                await asyncio.sleep(self.poll_interval)
                elapsed += self.poll_interval
                check_count += 1
                
                # 查询订单状态
                self.order = await loop.run_in_executor(
                    None, self._get_order_status, order_id
                )
                
                # 显示进度（每5次显示一次）
                if check_count % 5 == 0:
                    fill_pct = (self.order.filled_sz / self.order.sz * 100) if self.order.sz > 0 else 0
                    print(f"   ⏱️  已等待 {elapsed:.1f}秒 | 成交进度: {fill_pct:.1f}% ({self.order.filled_sz:.0f}/{self.order.sz:.0f})")
                
                # 检查是否完全成交
                if self.order.status == "filled":
                    total_time = time.time() - self.start_time
                    
                    print(f"\n{'='*70}")
                    print(f"✅ 限价单成交")
                    print(f"{'='*70}")
                    print(f"   订单ID: {self.order.order_id}")
                    print(f"   成交量: {self.order.filled_sz:.0f} 张")
                    print(f"   成交价: {self.order.avg_px:.2f}")
                    print(f"   总耗时: {total_time:.2f}秒")
                    print(f"{'='*70}\n")
                    
                    return {
                        "success": True,
                        "order_id": self.order.order_id,
                        "filled_sz": self.order.filled_sz,
                        "avg_px": self.order.avg_px,
                        "execution_type": "limit",
                        "total_time": total_time
                    }
            
            # 5. 超时处理：撤单 + 市价单
            print(f"\n⏰ 超时（{self.wait_time}秒）！改用市价单...")
            
            # 5.1 撤单
            print(f"   📋 撤销限价单...")
            cancel_success = await loop.run_in_executor(
                None, self._cancel_order, order_id
            )
            
            if cancel_success:
                print(f"   ✅ 限价单已撤销")
            else:
                print(f"   ⚠️ 撤单失败（可能已成交）")
            
            # 等待撤单生效
            await asyncio.sleep(0.5)
            
            # 5.2 查询最新状态
            self.order = await loop.run_in_executor(
                None, self._get_order_status, order_id
            )
            
            remain_sz = self.order.sz - self.order.filled_sz
            
            print(f"   📊 限价单状态: {self.order.status}")
            print(f"   📊 已成交: {self.order.filled_sz:.0f}/{self.order.sz:.0f}")
            print(f"   📊 剩余: {remain_sz:.0f} 张")
            
            if remain_sz <= 0:
                print(f"   ℹ️ 限价单已完全成交，无需市价单")
                
                total_time = time.time() - self.start_time
                
                return {
                    "success": True,
                    "order_id": self.order.order_id,
                    "filled_sz": self.order.filled_sz,
                    "avg_px": self.order.avg_px,
                    "execution_type": "limit",
                    "total_time": total_time
                }
            
            # 5.3 下市价单
            print(f"\n💥 下市价单成交剩余 {remain_sz:.0f} 张...")
            market_order_id = await loop.run_in_executor(
                None, self._place_market_order, remain_sz
            )
            print(f"   ✅ 市价单已提交: {market_order_id}")
            
            # 等待市价单成交
            await asyncio.sleep(2)
            
            # 查询市价单状态
            market_order = await loop.run_in_executor(
                None, self._get_order_status, market_order_id
            )
            
            total_time = time.time() - self.start_time
            
            # 计算综合成交价
            total_filled = self.order.filled_sz + market_order.filled_sz
            if total_filled > 0:
                avg_px = (
                    self.order.filled_sz * self.order.avg_px +
                    market_order.filled_sz * market_order.avg_px
                ) / total_filled
            else:
                avg_px = 0.0
            
            print(f"\n{'='*70}")
            print(f"✅ 混合成交完成")
            print(f"{'='*70}")
            print(f"   限价单: {self.order.filled_sz:.0f} 张 @ {self.order.avg_px:.2f}")
            print(f"   市价单: {market_order.filled_sz:.0f} 张 @ {market_order.avg_px:.2f}")
            print(f"   总成交: {total_filled:.0f} 张")
            print(f"   综合价: {avg_px:.2f}")
            print(f"   总耗时: {total_time:.2f}秒")
            print(f"{'='*70}\n")
            
            return {
                "success": True,
                "order_id": market_order_id,
                "filled_sz": total_filled,
                "avg_px": avg_px,
                "execution_type": "mixed",
                "limit_filled": self.order.filled_sz,
                "market_filled": market_order.filled_sz,
                "total_time": total_time
            }
            
        except Exception as e:
            print(f"\n❌ 下单失败: {e}")
            
            # 清理：如果有订单，尝试撤销
            if self.order and self.order.order_id:
                try:
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None, self._cancel_order, self.order.order_id
                    )
                except:
                    pass
            
            return {
                "success": False,
                "error": str(e)
            }


# ============================================================================
# 便捷函数
# ============================================================================

def place_inverse_perp_async(
    inst_id: str,
    side: Side,
    crypto_notional: float,
    simulated: bool = False,
    wait_time: float = 30.0,
    poll_interval: float = 0.5
) -> Dict[str, Any]:
    """
    便捷函数：异步下单 Inverse Perpetual Contract
    
    策略：
    1. Long: 在 ask-1 挂限价单
    2. Short: 在 bid+1 挂限价单
    3. 等待 wait_time 秒
    4. 超时则撤单，改用 market order
    
    Args:
        inst_id: 合约标识（如 "ETH-USD-SWAP"）
        side: 方向 "long" 或 "short"
        crypto_notional: 交易数量（币本位）
        simulated: 是否模拟盘
        wait_time: 等待时间（秒），默认30秒
        poll_interval: 轮询间隔（秒），默认0.5秒
    
    Returns:
        执行结果
    
    Example:
        # Long 1 ETH，等待30秒
        result = place_inverse_perp_async(
            inst_id="ETH-USD-SWAP",
            side="long",
            crypto_notional=1.0,
            simulated=True,
            wait_time=30.0
        )
        
        # Short 2 ETH，等待1分钟
        result = place_inverse_perp_async(
            inst_id="ETH-USD-SWAP",
            side="short",
            crypto_notional=2.0,
            simulated=True,
            wait_time=60.0
        )
    """
    placer = AsyncInversePerpPlacer(
        inst_id=inst_id,
        side=side,
        crypto_notional=crypto_notional,
        simulated=simulated,
        wait_time=wait_time,
        poll_interval=poll_interval
    )
    
    return asyncio.run(placer.execute())

