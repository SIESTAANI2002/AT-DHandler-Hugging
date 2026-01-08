import logging
import asyncio
from pyrogram.errors import FloodWait

class ByteStreamer:
    def __init__(self, client):
        self.client = client

    async def yield_file(self, file_id, index, first_part_cut, last_part_cut, part_count, chunk_size=1024 * 1024):
        """
        FileStreamBot Style Yielding
        index: কত তম চাঙ্ক থেকে শুরু হবে
        part_count: মোট কতগুলো চাঙ্ক লাগবে
        """
        client = self.client
        
        try:
            async for chunk in client.stream_media(
                file_id,
                limit=part_count,
                offset=index,
            ):
                if not chunk:
                    break
                
                # প্রথম চাঙ্ক প্রসেসিং (Cutting logic)
                if first_part_cut:
                    yield chunk[first_part_cut:]
                    first_part_cut = 0 # একবার কাটার পর আর কাটার দরকার নেই
                
                # শেষ চাঙ্ক প্রসেসিং
                elif last_part_cut and part_count == 1:
                    yield chunk[:last_part_cut]
                    break
                
                # সাধারণ চাঙ্ক
                else:
                    yield chunk
                
                part_count -= 1
                
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            logging.error(f"ByteStreamer Error: {e}")
            pass
