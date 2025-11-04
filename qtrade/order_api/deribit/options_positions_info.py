#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Deribit Options Position Information Module - 精确P&L版本
基于 private/get_account_summary 获取最精确的P&L数据，专为对冲交易设计
"""

from qtrade.order_api.deribit.options_order import DERIBIT_BASE, _authenticated_request
from qtrade.order_api.deribit.current_balance import get_account_summary



def get_instrument_pnl(instrument_name: str, env: str = "testnet") -> float:
    """
    获取指定合约的精确P&L - 基于账户汇总API
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-28NOV25-114000-C"
        env: 交易环境
        
    Returns:
        float: 精确未实现P&L (BTC单位)
    """
    try:
        # 从合约名称提取币种
        currency = instrument_name.split('-')[0]  # BTC-28NOV25-114000-C -> BTC
        
        # 获取账户汇总中的精确P&L
        account_summary = get_account_summary(currency, env)
        precise_pnl = account_summary.get("total_pl", 0.0)
        
        return precise_pnl
        
    except Exception as e:
        print(f"❌ 获取合约P&L失败 {instrument_name}: {e}")
        return 0.0


def get_instrument_open_price(instrument_name: str, env: str = "testnet"):
    """
    获取指定合约的开仓价格 - 基于position API
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-28NOV25-114000-C"
        env: 交易环境
        
    Returns:
        float: 开仓价格 (average_price)
    """
    try:
        # 调用 private/get_position API
        params = {"instrument_name": instrument_name}
        result = _authenticated_request("GET", "private/get_position", params, env)
        
        # 直接返回average_price字段
        return result.get("average_price", 0.0)
        
    except Exception as e:
        print(f"❌ 获取合约开仓价格失败 {instrument_name}: {e}")
        return 0.0 


def get_instrument_position_size(instrument_name: str, env: str = "testnet") -> float:
    """
    获取指定合约的仓位大小
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-28NOV25-114000-C"
        env: 交易环境
        
    Returns:
        float: 仓位大小 (正数=多头，负数=空头，0=无仓位)
    """
    try:
        params = {"instrument_name": instrument_name}
        result = _authenticated_request("GET", "private/get_position", params, env)
        return result.get("size", 0.0)
    except Exception as e:
        print(f"❌ 获取合约仓位大小失败 {instrument_name}: {e}")
        return 0.0
def get_instrument_orderbook(instrument_name: str, env: str = "testnet"):
    """
    获取指定合约的完整订单簿信息（包括IV）
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-28NOV25-114000-C"
        env: 交易环境
        
    Returns:
        dict: 包含IV和订单簿信息的字典
    """
    try:
        import requests
        
        # 直接调用 public/get_order_book API
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/get_order_book"
        
        params = {
            "instrument_name": instrument_name,
            "depth": 1
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("error"):
            print(f"❌ API错误: {data['error']}")
            return {}


        print(data)
        
        result = data.get("result", {})
        
        bids = result.get("bids", [])
        asks = result.get("asks", [])
        
        best_bid = bids[0][0] if bids else 0
        best_ask = asks[0][0] if asks else 0
        
        return {
            "instrument": instrument_name,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": best_ask - best_bid if best_bid > 0 and best_ask > 0 else 0,
            "mid_price": (best_bid + best_ask) / 2 if best_bid > 0 and best_ask > 0 else 0,
            "mark_price": result.get("mark_price", 0),
            "mark_iv": result.get("mark_iv", 0.0) / 100.0,  # 转换为小数形式
            "timestamp": result.get("timestamp", ""),
            "greeks": result.get("greeks", {}),  # 如果有希腊字母数据
        }
        
    except Exception as e:
        print(f"❌ 获取合约订单簿失败 {instrument_name}: {e}")
        return {}


def get_instrument_iv(instrument_name: str, env: str = "testnet") -> float:
    """
    获取指定合约的隐含波动率(IV) - 从订单簿数据中获取
    
    Args:
        instrument_name: 期权合约名称，如 "BTC-28NOV25-114000-C"
        env: 交易环境
        
    Returns:
        float: 隐含波动率 (mark_iv，已转换为小数形式)
    """
    try:
        import requests
        
        # 使用 public/get_order_book API 获取订单簿数据（包含IV）
        base = DERIBIT_BASE[env]
        url = f"{base}/api/v2/public/get_order_book"
        
        params = {
            "instrument_name": instrument_name,
            "depth": 1
        }
        
        response = requests.get(url, params=params)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("error"):
            print(f"❌ API错误: {data['error']}")
            return 0.0
        
        result = data.get("result", {})
        
        # 获取mark_iv并转换为小数形式
        mark_iv = result.get("mark_iv", 0.0)
        
        # Deribit返回的IV通常是百分比形式，需要除以100转换为小数
        if mark_iv > 0:
            return mark_iv / 100.0
        
        return 0.0
        
    except Exception as e:
        print(f"❌ 获取合约IV失败 {instrument_name}: {e}")
        return 0.0