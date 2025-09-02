# tardis api key:TD.sDyJS7YZ6oPWSgy2.-vZySO46Lv8avKO.ixQvOq9xdhxqnzC.p1rlPahcqt4F3pp.uORrUOeq0hqYOhV.w6s4

#文档见tardis官网QAQ
# 例子：
# requires Python >=3.6
# pip install tardis-dev
API="TD.sDyJS7YZ6oPWSgy2.-vZySO46Lv8avKO.ixQvOq9xdhxqnzC.p1rlPahcqt4F3pp.uORrUOeq0hqYOhV.w6s4"
import nest_asyncio
nest_asyncio.apply()
from tardis_dev import datasets, get_exchange_details
import logging

import nest_asyncio
nest_asyncio.apply()
# optionally enable debug logs
# logging.basicConfig(level=logging.DEBUG)

exchange = 'okex-options'  #okex，binance等
exchange_details = get_exchange_details(exchange)


time_frames = [
    ["2024-01-21T00:00:00.000Z", "2024-01-22T00:00:00.000Z"],
    ["2024-04-02T00:00:00.000Z", "2024-04-03T00:00:00.000Z"],
    ["2024-04-15T00:00:00.000Z", "2024-04-16T00:00:00.000Z"],
    ["2024-06-27T00:00:00.000Z", "2024-06-28T00:00:00.000Z"],
]

# iterate over and download all data for every symbol
for symbol in exchange_details["datasets"]["symbols"]:
    # alternatively specify datatypes explicitly ['trades', 'incremental_book_L2', 'quotes'] etc
    # see available options https://docs.tardis.dev/downloadable-csv-files#data-types
    data_types = symbol["dataTypes"]
    symbol_id = symbol["id"]
    from_date =  symbol["availableSince"]
    to_date = symbol["availableTo"]


    print(symbol['id'])

    # skip groupped symbols
    if symbol_id in ['PERPETUALS', 'SPOT', 'FUTURES']:
        continue
    
    print(f"symbol_id: {symbol_id}")
    print(f"from_date: {type(from_date)}")
    print(f"to_date: {to_date}")
    print(f"data_types: {data_types}")
    
    # from_date = "2015-08-01T00:00:00.000Z"
    print(f"data_types: {data_types}")
    data_types = ['quotes']

    for time_frame in time_frames:
    
        from_date = time_frame[0]
        to_date = time_frame[1]
        
        print(f"Downloading {exchange} {data_types} for {symbol_id} from {from_date} to {to_date}")

        
        
        # each CSV dataset format is documented at https://docs.tardis.dev/downloadable-csv-files#data-types
        # see https://docs.tardis.dev/downloadable-csv-files#download-via-client-libraries for full options docs
        datasets.download(
            exchange = exchange,
            data_types = data_types,
            from_date =  from_date,
            to_date = to_date,
            symbols = [symbol_id],
            # TODO set your API key here
            api_key = API,
            # path where CSV data will be downloaded into
            download_dir = "/data/option_data/okx_datasets4_makeup",
        )
