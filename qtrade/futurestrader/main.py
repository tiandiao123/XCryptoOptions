from qtrade.futurestrader.arbitrage_finder import aggregate_topk_from_three


if __name__ == "__main__":
    funding_rate_arbitrage_opportunities = aggregate_topk_from_three(top_n_each=40, top_k=20)

    for opportunity in funding_rate_arbitrage_opportunities:
        print(opportunity)