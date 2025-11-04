

import yaml

from qtrade.optionstrader.arbitrage_searcher.calendar_spread.atm_options_okx import get_okx_atm_options
from qtrade.optionstrader.arbitrage_searcher.calendar_spread.calendar_spread_finder import display_calendar_opportunities, find_calendar_spread_options


def get_calender_spread_order(config_path: str, currency: str = "ETH"):


    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # 1. 获取ATM期权（来自atm_options_filter.py）
    atm_options = get_okx_atm_options(config, "ETH")

    for opt in atm_options:
        print("================================================")
        print(f"📌 {opt.symbol}")
        print(f"   执行价: ${opt.strike:,.2f}")
        print(f"   报价: Bid ${opt.bid:,.4f} / Ask ${opt.ask:,.4f} / Mid ${opt.mid_price:,.4f}")
        print(f"   波动率(IV): {opt.iv:.2%}")
        print(f"   持仓量(OI): {opt.open_interest}")
        print(f"   希腊字母: Δ {opt.delta:+.4f} | Γ {opt.gamma:+.4f} | ν {opt.vega:+.4f} | Θ {opt.theta:+.4f} | ρ {opt.rho:+.4f}")
        print(f"   到期: {opt.expiry} | 剩余: {opt.days_to_expiry} 天 | 类型: {opt.option_type}")
        print("================================================")
        print("\n")

    # 2. 搜索Calendar Spread机会
    opportunities = find_calendar_spread_options(atm_options, config)

    # 3. 显示结果
    display_calendar_opportunities(opportunities)

    return opportunities[0]



if __name__ == "__main__":
    calendar_config_path = "/home/ubuntu/options_trading/qtrade/optionstrader/arbitrage_searcher/calendar_spread/calendar_spread.yaml"
    opportunity = get_calender_spread_order(calendar_config_path, "ETH")
    print(opportunity)

