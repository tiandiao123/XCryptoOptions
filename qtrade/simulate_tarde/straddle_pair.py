import re
from datetime import datetime, date
from qtrade.data_utils import get_option_open_price

def parse_option_expiry_date(symbol):
    """从期权符号解析到期日"""
    match = re.search(r'BTC-USD-(\d{6})-', symbol)
    if match:
        date_str = match.group(1)  # YYMMDD
        year = 2000 + int(date_str[:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])
        return date(year, month, day)
    return None

class StraddlePair:
    """
    Straddle策略组合类
    
    Long Straddle: 买入相同执行价格的Call和Put (看大波动)
    Short Straddle: 卖出相同执行价格的Call和Put (看小波动)
    """
    
    def __init__(self, call_option, put_option, entry_time, entry_spot_price, strategy_type="long"):
        """
        初始化Straddle组合
        
        Args:
            call_option: Call期权信息字典 {'symbol': str, 'open': float, 'strike_price': float, ...}
            put_option: Put期权信息字典
            entry_time: 入场时间
            entry_spot_price: 入场时现货价格
            strategy_type: 策略类型 "long" 或 "short"
        """
        self.entry_time = entry_time
        self.entry_spot_price = entry_spot_price
        self.strategy_type = strategy_type.lower()
        
        # 期权价格
        self.call_price = call_option['open']
        self.put_price = put_option['open']
        
        # 执行价格（Straddle中Call和Put应该有相同执行价格）
        self.strike_price = call_option['strike_price']
        if abs(call_option['strike_price'] - put_option['strike_price']) > 1e-6:
            print(f"⚠️  警告: Call执行价({call_option['strike_price']}) != Put执行价({put_option['strike_price']})")
        
        # 入场权利金计算
        if self.strategy_type == "long":
            # Long Straddle: 买入Call + 买入Put (支付权利金)
            self.entry_premium = -(self.call_price + self.put_price)  # 负数表示支付
        else:
            # Short Straddle: 卖出Call + 卖出Put (收取权利金)
            self.entry_premium = self.call_price + self.put_price     # 正数表示收取
        
        # 盈亏跟踪
        self.current_pnl = 0.0
        self.is_active = True
        self.last_update_time = entry_time
        
        # 存储期权符号以便查询
        self.option_symbols = {
            'call': call_option['symbol'],
            'put': put_option['symbol']
        }
        
        # 存储期权的其他信息
        self.call_info = call_option.copy()
        self.put_info = put_option.copy()
        
        print(f"✅ {self.strategy_type.title()} Straddle创建:")
        print(f"   执行价格: ${self.strike_price:,.2f}")
        print(f"   入场现货价: ${entry_spot_price:,.2f}")
        print(f"   入场权利金: {self.entry_premium:.6f} BTC")
        print(f"   Call价格: {self.call_price:.6f} BTC")
        print(f"   Put价格: {self.put_price:.6f} BTC")
    
    def update_pnl(self, current_time, current_df, current_spot_price=None, print_info=False):
        """
        更新当前盈亏
        
        Args:
            current_time: 当前时间点
            current_df: 当前时间点的期权数据DataFrame
            current_spot_price: 当前现货价格（可选）
            print_info: 是否打印详细信息
        
        Returns:
            tuple: (success, reason)
        """
        if not self.is_active:
            if print_info:
                print("⚠️  组合已平仓，无法更新P&L")
            return False, "position_closed"
        
        # 检查期权是否已到期
        current_date = current_time.date()
        expired_options = []
        
        for position, symbol in self.option_symbols.items():
            expiry_date = parse_option_expiry_date(symbol)
            if expiry_date and current_date >= expiry_date:
                expired_options.append((position, symbol, expiry_date))
        
        if expired_options:
            if print_info:
                print(f"⚠️  以下期权已到期:")
                for pos, sym, exp_date in expired_options:
                    print(f"     {pos}: {sym} (到期日: {exp_date})")
            return False, "options_expired"
        
        try:
            # 获取Call和Put的当前价格
            current_call_price = get_option_open_price(
                current_df, 
                self.option_symbols['call'], 
                current_time, 
                print_info=False
            )
            
            current_put_price = get_option_open_price(
                current_df, 
                self.option_symbols['put'], 
                current_time, 
                print_info=False
            )
            
            # 检查是否成功获取价格
            if current_call_price is None or current_put_price is None:
                missing = []
                if current_call_price is None:
                    missing.append(self.option_symbols['call'])
                if current_put_price is None:
                    missing.append(self.option_symbols['put'])
                
                if print_info:
                    print(f"⚠️  无法获取期权价格，缺失: {missing}")
                return False, f"missing_prices: {missing}"
            
            # 更新当前价格
            self.call_price = current_call_price
            self.put_price = current_put_price
            
            # 计算当前组合价值
            if self.strategy_type == "long":
                # Long Straddle: 持有Call + 持有Put
                current_premium = -(current_call_price + current_put_price)
            else:
                # Short Straddle: 空头Call + 空头Put
                current_premium = current_call_price + current_put_price
            
            # 计算P&L
            self.current_pnl = current_premium - self.entry_premium
            self.last_update_time = current_time
            
            if print_info:
                print(f"📊 Straddle P&L更新 - 时间: {current_time.strftime('%Y-%m-%d %H:%M')}")
                print(f"   策略类型: {self.strategy_type.title()} Straddle")
                print(f"   执行价格: ${self.strike_price:,.2f}")
                print(f"   入场权利金: {self.entry_premium:.6f} BTC")
                print(f"   当前权利金: {current_premium:.6f} BTC")
                print(f"   当前P&L: {self.current_pnl:.6f} BTC")
                print(f"   Call价格: {current_call_price:.6f} BTC")
                print(f"   Put价格: {current_put_price:.6f} BTC")
                
                if current_spot_price:
                    print(f"   现货价格: ${current_spot_price:,.2f}")
                    print(f"   价格变化: {(current_spot_price - self.entry_spot_price) / self.entry_spot_price * 100:+.2f}%")
                    moneyness = current_spot_price / self.strike_price
                    print(f"   Moneyness: {moneyness:.3f}")
            
            return True, "success"
            
        except Exception as e:
            if print_info:
                print(f"❌ 更新P&L失败: {e}")
            return False, f"exception: {str(e)}"
    
    def should_close(self, current_time, current_spot_price=None, max_loss_pct=0.3, target_profit_pct=0.5, price_threshold_pct=0.15):
        """
        Straddle平仓条件检查
        
        Args:
            current_time: 当前时间
            current_spot_price: 当前现货价格
            max_loss_pct: 最大亏损百分比
            target_profit_pct: 目标盈利百分比
            price_threshold_pct: 价格突破阈值百分比（相对于执行价格）
            
        Returns:
            tuple: (should_close, reason)
        """
        if not self.is_active:
            return False, "已平仓"
        
        # 计算P&L百分比
        if abs(self.entry_premium) > 1e-8:
            pnl_pct = self.current_pnl / abs(self.entry_premium)
        else:
            pnl_pct = 0
        
        # 止损条件
        if pnl_pct < -max_loss_pct:
            return True, f"止损 (P&L: {pnl_pct*100:.1f}%)"
        
        # 止盈条件
        if pnl_pct > target_profit_pct:
            return True, f"止盈 (P&L: {pnl_pct*100:.1f}%)"
        
        # Straddle特有的平仓条件
        if current_spot_price is not None:
            price_move_pct = abs(current_spot_price - self.strike_price) / self.strike_price
            
            if self.strategy_type == "long":
                # Long Straddle: 价格大幅偏离执行价格时可能获利
                if price_move_pct > price_threshold_pct:
                    direction = "上涨" if current_spot_price > self.strike_price else "下跌"
                    return True, f"价格大幅{direction} (偏离执行价{price_move_pct*100:.1f}%)"
            else:
                # Short Straddle: 价格靠近执行价格时获利，远离时亏损
                if price_move_pct > price_threshold_pct:
                    direction = "上涨" if current_spot_price > self.strike_price else "下跌"
                    return True, f"价格大幅{direction}，风险增加 (偏离执行价{price_move_pct*100:.1f}%)"
        
        return False, "持续持有"
    
    def get_current_status(self):
        """获取当前状态信息"""
        return {
            'is_active': self.is_active,
            'strategy_type': self.strategy_type,
            'entry_time': self.entry_time,
            'entry_spot_price': self.entry_spot_price,
            'strike_price': self.strike_price,
            'entry_premium': self.entry_premium,
            'current_pnl': self.current_pnl,
            'last_update_time': self.last_update_time,
            'call_price': self.call_price,
            'put_price': self.put_price,
            'option_symbols': self.option_symbols.copy()
        }
    
    def close(self, close_time=None, close_reason="手动平仓"):
        """
        平仓
        
        Args:
            close_time: 平仓时间
            close_reason: 平仓原因
            
        Returns:
            dict: 平仓信息
        """
        if not self.is_active:
            return None
        
        close_info = {
            'strategy_type': self.strategy_type,
            'entry_time': self.entry_time,
            'close_time': close_time or self.last_update_time,
            'strike_price': self.strike_price,
            'entry_premium': self.entry_premium,
            'final_pnl': self.current_pnl,
            'close_reason': close_reason,
            'pnl_pct': self.current_pnl / abs(self.entry_premium) if abs(self.entry_premium) > 1e-8 else 0
        }
        
        self.is_active = False
        return close_info
    
    def calculate_breakeven_points(self):
        """计算盈亏平衡点"""
        premium_total = abs(self.entry_premium)
        
        if self.strategy_type == "long":
            # Long Straddle盈亏平衡点: Strike ± Premium
            upper_breakeven = self.strike_price + premium_total
            lower_breakeven = self.strike_price - premium_total
        else:
            # Short Straddle盈亏平衡点: Strike ± Premium
            upper_breakeven = self.strike_price + premium_total
            lower_breakeven = self.strike_price - premium_total
        
        return {
            'upper_breakeven': upper_breakeven,
            'lower_breakeven': lower_breakeven,
            'strike_price': self.strike_price,
            'premium_paid': premium_total
        }
    
    def get_profit_profile(self, spot_prices):
        """
        计算在不同现货价格下的盈亏情况
        
        Args:
            spot_prices: 现货价格列表
            
        Returns:
            list: 对应的盈亏列表
        """
        profits = []
        premium_total = abs(self.entry_premium)
        
        for spot in spot_prices:
            if self.strategy_type == "long":
                # Long Straddle: max(S-K, 0) + max(K-S, 0) - Premium
                call_value = max(spot - self.strike_price, 0)
                put_value = max(self.strike_price - spot, 0)
                profit = call_value + put_value - premium_total
            else:
                # Short Straddle: Premium - max(S-K, 0) - max(K-S, 0)
                call_value = max(spot - self.strike_price, 0)
                put_value = max(self.strike_price - spot, 0)
                profit = premium_total - call_value - put_value
            
            profits.append(profit)
        
        return profits


# 工具函数：创建Straddle策略
def create_straddle_from_atm_options(atm_options, strategy_type="long", target_dte_range=(20, 40)):
    """
    从ATM期权列表创建Straddle策略
    
    Args:
        atm_options: ATM期权列表
        strategy_type: "long" 或 "short"
        target_dte_range: 目标到期天数范围
        
    Returns:
        dict: Straddle配置信息，如果找不到合适期权则返回None
    """
    # 筛选目标到期时间范围的期权
    target_options = [
        opt for opt in atm_options 
        if target_dte_range[0] <= opt['days_to_expiry'] <= target_dte_range[1]
    ]
    
    if not target_options:
        return None
    
    # 按到期时间和距离ATM的远近排序
    target_options.sort(key=lambda x: (x['days_to_expiry'], abs(x['moneyness'] - 1.0)))
    
    # 寻找相同执行价格的Call和Put
    calls = [opt for opt in target_options if opt['option_type'] == 'C']
    puts = [opt for opt in target_options if opt['option_type'] == 'P']
    
    for call_opt in calls:
        for put_opt in puts:
            # 检查是否为相同执行价格和到期日
            if (abs(call_opt['strike_price'] - put_opt['strike_price']) < 1e-6 and
                abs(call_opt['days_to_expiry'] - put_opt['days_to_expiry']) <= 1):
                
                return {
                    'call_option': call_opt,
                    'put_option': put_opt,
                    'strategy_type': strategy_type,
                    'strike_price': call_opt['strike_price'],
                    'days_to_expiry': call_opt['days_to_expiry'],
                    'combined_premium': call_opt['open'] + put_opt['open']
                }
    
    return None


if __name__ == "__main__":
    print("🧪 StraddlePair 测试")
    print("="*40)
    
    # 模拟期权数据
    from datetime import datetime
    
    call_option = {
        'symbol': 'BTC-USD-250131-95000-C',
        'open': 0.02500,
        'strike_price': 95000,
        'option_type': 'C',
        'days_to_expiry': 30
    }
    
    put_option = {
        'symbol': 'BTC-USD-250131-95000-P',
        'open': 0.02300,
        'strike_price': 95000,
        'option_type': 'P',
        'days_to_expiry': 30
    }
    
    entry_time = datetime.now()
    entry_spot = 95000
    
    # 测试Long Straddle
    print("\n📊 测试 Long Straddle:")
    long_straddle = StraddlePair(call_option, put_option, entry_time, entry_spot, "long")
    
    # 计算盈亏平衡点
    breakeven = long_straddle.calculate_breakeven_points()
    print(f"\n盈亏平衡点:")
    print(f"   上方: ${breakeven['upper_breakeven']:,.2f}")
    print(f"   下方: ${breakeven['lower_breakeven']:,.2f}")
    
    # 测试不同价格下的盈亏
    test_prices = [90000, 92000, 95000, 98000, 100000]
    profits = long_straddle.get_profit_profile(test_prices)
    
    print(f"\n不同价格下的理论盈亏:")
    for price, profit in zip(test_prices, profits):
        print(f"   ${price:,.0f}: {profit:+.6f} BTC")
    
    # 测试Short Straddle
    print(f"\n📊 测试 Short Straddle:")
    short_straddle = StraddlePair(call_option, put_option, entry_time, entry_spot, "short")
    
    profits_short = short_straddle.get_profit_profile(test_prices)
    print(f"\nShort Straddle不同价格下的理论盈亏:")
    for price, profit in zip(test_prices, profits_short):
        print(f"   ${price:,.0f}: {profit:+.6f} BTC")
    
    print(f"\n✅ StraddlePair 测试完成!")
