import time
from qtrade.cryptotrader.arbitrage_searcher.calendar_spread_manager import CalendarSpreadManager
from qtrade.cryptotrader.arbitrage_searcher.gamma_scalping_manager import GammaScalpingSellStraddleManager


class TradingEngine:
    def __init__(self, 
                 calendar_config_path: str, 
                 gamma_scalping_config_path: str,
                 env: str = "testnet", 
                 max_open_calendar: int = 1, 
                 max_open_gamma_scalping: int = 1):
        self.env = env 
        self.calendar_spread_manager = CalendarSpreadManager(calendar_config_path, env)
        self.gamma_scalping_sell_straddle_manager = GammaScalpingSellStraddleManager(gamma_scalping_config_path, env)


        self.calendar_opportunities = []
        self.gamma_scalping_opportunities = []
    
    def _transform_check_durantion(self, check_durantion: str):
        if check_durantion == "5min":
            check_durantion = 300
        elif check_durantion == "10min":
            check_durantion = 600
        elif check_durantion == "15min":
            check_durantion = 900
        elif check_durantion == "30min":
            check_durantion = 1800
        return check_durantion

    def run_loop(self, check_durantion: str = "5min"):
        
        assert check_durantion in ["5min", "10min", "15min", "30min"], "check_durantion must be 5min, 10min, 15min or 30min"
        check_durantion = self._transform_check_durantion(check_durantion)

        while True:
            calendar_opportunities = self.calendar_spread_manager.check_opportunities()
            gamma_scalping_opportunities = self.gamma_scalping_sell_straddle_manager.check_opportunities()
            
            if len(self.calendar_opportunities) < self.max_open_calendar: 
                if calendar_opportunities is not None and len(calendar_opportunities) > 0:
                    # open calendar opportunities   
                    pass 

            if len(self.gamma_scalping_opportunities) < self.max_open_gamma_scalping:
                if gamma_scalping_opportunities is not None and len(gamma_scalping_opportunities) > 0:
                    # open gamma scalping opportunities
                    pass 

            
            time.sleep(check_durantion)
    
    def check_close(self):
        pass 
    

    def record_pnl(self, ): 
        # get account info 
        pass 
