# pip install tardis-client
import asyncio
from tardis_client import TardisClient, Channel
tardis_client = TardisClient(api_key="TD.sDyJS7YZ6oPWSgy2.-vZySO46Lv8avKO.ixQvOq9xdhxqnzC.p1rlPahcqt4F3pp.uORrUOeq0hqYOhV.w6s4")

async def replay():
  # replay method returns Async Generator
  messages = tardis_client.replay(
    exchange="okex-options",
    from_date="2020-02-01",
    to_date="2020-02-02",
    filters=[Channel(name="option/trade", symbols=[])]
  )

  # messages as provided by OKEx real-time stream
  async for local_timestamp, message in messages:
    print(message)


asyncio.run(replay())