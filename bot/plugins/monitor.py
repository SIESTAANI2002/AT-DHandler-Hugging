import asyncio
import psutil
from bot.utils.database import db

async def bandwidth_monitor():
    io = psutil.net_io_counters()
    last_sent = io.bytes_sent
    last_recv = io.bytes_recv

    while True:
        await asyncio.sleep(20) # ২০ সেকেন্ড পর পর চেক

        try:
            io = psutil.net_io_counters()
            curr_sent = io.bytes_sent
            curr_recv = io.bytes_recv

            sent_delta = curr_sent - last_sent
            recv_delta = curr_recv - last_recv

            if sent_delta < 0: sent_delta = curr_sent
            if recv_delta < 0: recv_delta = curr_recv

            last_sent = curr_sent
            last_recv = curr_recv

            if sent_delta > 0 or recv_delta > 0:
                # 🔥 Oracle Bandwidth সেভ করা হচ্ছে
                await db.add_streamer_bandwidth(sent_delta, recv_delta)

            # 🔥 Monthly Reset চেক
            await db.check_streamer_reset()

        except Exception as e:
            print(f"Monitor Error: {e}")
