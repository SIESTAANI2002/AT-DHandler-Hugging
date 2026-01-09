import math
import logging
from aiohttp import web
from urllib.parse import quote 
from pyrogram.types import Message
from pyrogram.errors import FileReferenceExpired

# Logging Setup
logger = logging.getLogger(__name__)
TG_CHUNK = 1024 * 1024  # 1MB Telegram Chunk Size

# --- 🛠️ Custom ByteStreamer Class (Fixed) ---
class ByteStreamer:
    def __init__(self, client, message: Message):
        self.client = client
        self.message = message
        self.media = getattr(message, message.media.value)
        self.file_id = self.media.file_id

    async def yield_chunk(self, offset=0, length=-1):
        """
        এই জেনারেটর ফাংশনটি ফাইল ডাউনলোড করে এবং ব্রাউজারে পাঠায়।
        এখানেই আমরা FileReferenceExpired এরর হ্যান্ডেল করব।
        """
        try:
            # পাইরোগ্রামের স্মার্ট স্ট্রিমার ব্যবহার করা হচ্ছে
            async for chunk in self.client.stream_media(
                message=self.message,
                offset=offset,
                limit=length
            ):
                yield chunk

        except FileReferenceExpired:
            # ⚠️ যদি মাঝপথে এরর আসে, আমরা মেসেজ রিফ্রেশ করব
            logger.warning(f"⚠️ Stream Error: FileReferenceExpired for {self.file_id}. Refreshing...")
            
            try:
                # ১. মেসেজ রিফ্রেশ (Telegram থেকে নতুন রেফারেন্স আনা)
                refresh_msg = await self.client.get_messages(
                    chat_id=self.message.chat.id,
                    message_ids=self.message.id
                )
                
                # ২. নতুন মেসেজ অবজেক্ট আপডেট করা
                self.message = refresh_msg
                self.media = getattr(refresh_msg, refresh_msg.media.value)

                # ৩. আবার ডাউনলোড শুরু করা (Retry)
                async for chunk in self.client.stream_media(
                    message=self.message,
                    offset=offset,
                    limit=length
                ):
                    yield chunk
                    
            except Exception as e:
                logger.error(f"❌ Refresh Failed inside Streamer: {e}")
                # এখানে আর কিছু করার নেই, কানেকশন ড্রপ হবে
                raise e

# --- CORS Headers ---
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, User-Agent",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range",
    }

# --- 🔥 Main Media Streamer Function ---
async def media_streamer(request, message: Message, custom_file_name=None):
    try:
        media = getattr(message, message.media.value, None)
        if not media:
            raise web.HTTPNotFound(text="Media not found")

        file_size = media.file_size

        # --- FILENAME LOGIC ---
        if custom_file_name:
            file_name = custom_file_name
        else:
            file_name = getattr(media, "file_name", None) or f"AnimeToki_{message.id}.mp4"

        encoded_file_name = quote(file_name)
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # --- RANGE HEADER HANDLING ---
        range_header = request.headers.get("Range")
        start = 0
        end = file_size - 1
        status = 200

        if range_header:
            try:
                parts = range_header.replace("bytes=", "").split("-")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
                status = 206 # Partial Content
            except ValueError:
                status = 200 # Fallback

        if start >= file_size:
            return web.Response(
                status=416, 
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        # Length Calculation
        content_length = end - start + 1

        # --- HEADERS SETUP ---
        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'attachment; filename="{file_name}"; filename*=UTF-8\'\'{encoded_file_name}',
            "Content-Length": str(content_length),
        }
        headers.update(cors_headers())

        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        # --- STREAMING START ---
        # ⚠️ ক্লাস্টার ফিক্স: message._client ব্যবহার করছি যাতে সঠিক বট ডাউনলোড করে
        streamer = ByteStreamer(client=message._client, message=message)
        
        body = streamer.yield_chunk(offset=start, length=content_length)

        return web.Response(status=status, body=body, headers=headers)

    except Exception as e:
        logging.error(f"Stream Helper Error: {e}")
        raise web.HTTPInternalServerError()
