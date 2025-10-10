

from collections import deque
from typing import Any, Union
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping.selling_straddle_finder import StraddleOpportunity
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import CalendarSpreadOpportunity
from qtrade.cryptotrader.trading_engine.thread_safe_deque import ThreadSafeArrayDeque


class RiskManager:
    def __init__(self, max_positions: int = 1, enable_delta_hedge: bool = False):
        self.start_id = 0
        self.end_id = 0
        self.max_positions = max_positions
        self.enable_delta_hedge = enable_delta_hedge

        self.straddle_positions = ThreadSafeArrayDeque(max_capacity=max_positions, capacity=max_positions)
        self.calendar_spread_positions = ThreadSafeArrayDeque(max_capacity=max_positions, capacity=max_positions)
    

    def add_position(self, position: Union[StraddleOpportunity, CalendarSpreadOpportunity]):
        
        if isinstance(position, StraddleOpportunity) and self.can_add_straddle_position():
            self.straddle_positions.append(position)
        elif isinstance(position, CalendarSpreadOpportunity) and self.can_add_calendar_spread_position():
            self.calendar_spread_positions.append(position)
        else:
            raise ValueError(f"Invalid position type: {type(position)}")
        
    def can_add_straddle_position(self):
        return len(self.straddle_positions) < self.max_positions

    
    def monitor_positions(self):
        pass 