import math
import logging
from aiohttp import web
from urllib.parse import quote 
from pyrogram.types import Message
from pyrogram.errors import FileReferenceExpired

# 👇 আপনার রিকুয়েস্ট অনুযায়ী custom_dl ইমপোর্ট করা হলো
from bot.utils.custom_dl import ByteStreamer 

# Logging Setup
logger = logging.getLogger(__name__)
TG_CHUNK = 1024 * 1024  # 1MB Telegram Chunk Size

# --- CORS Headers ---
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, User-Agent",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range",
    }

# --- 🔄 RETRY GENERATOR (The Magic Fix) ---
async def yield_with_retry(client, message, file_id, chunk_index, first_part_cut, last_part_cut, part_count):
    """
    এই ফাংশনটি custom_dl কে কল করবে। 
    যদি FileReferenceExpired হয়, তাহলে মেসেজ রিফ্রেশ করে আবার custom_dl কল করবে।
    """
    try:
        # ১. সাধারণ চেষ্টা (Attempt 1)
        streamer = ByteStreamer(client)
        async for chunk in streamer.yield_file(file_id, chunk_index, first_part_cut, last_part_cut, part_count):
            yield chunk

    except FileReferenceExpired:
        # ⚠️ এরর ধরা পড়লে
        logger.warning(f"⚠️ FileRef Expired for {file_id}. Refreshing & Retrying...")
        
        try:
            # ২. মেসেজ রিফ্রেশ করে নতুন File ID আনা
            refresh_msg = await client.get_messages(chat_id=message.chat.id, message_ids=message.id)
            new_media = getattr(refresh_msg, refresh_msg.media.value)
            new_file_id = new_media.file_id # নতুন ফ্রেশ আইডি
            
            # ৩. আবার চেষ্টা (Attempt 2 with New ID)
            streamer = ByteStreamer(client)
            async for chunk in streamer.yield_file(new_file_id, chunk_index, first_part_cut, last_part_cut, part_count):
                yield chunk
                
        except Exception as e:
            logger.error(f"❌ Retry Failed: {e}")
            raise e

# --- 🔥 Main Media Streamer ---
async def media_streamer(request, message: Message, custom_file_name=None):
    try:
        media = getattr(message, message.media.value, None)
        if not media:
            raise web.HTTPNotFound(text="Media not found")

        file_id = media.file_id
        file_size = media.file_size

        # --- FILENAME ---
        if custom_file_name:
            file_name = custom_file_name
        else:
            file_name = getattr(media, "file_name", None) or f"AnimeToki_{message.id}.mp4"

        encoded_file_name = quote(file_name)
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # --- RANGE HEADER HANDLING (Math Logic) ---
        range_header = request.headers.get("Range")
        if range_header:
            try:
                start, end = range_header.replace("bytes=", "").split("-")
                start = int(start)
                end = int(end) if end else file_size - 1
                status = 206
            except ValueError:
                start = 0
                end = file_size - 1
                status = 200
        else:
            start = 0
            end = file_size - 1
            status = 200

        if start >= file_size:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{file_size}"})

        # --- 🧮 OFFSET CALCULATION (OffsetInvalid Fix) ---
        # এই ক্যালকুলেশনটি custom_dl এর জন্য খুবই জরুরি
        offset = start - (start % TG_CHUNK) 
        chunk_index = offset // TG_CHUNK
        first_part_cut = start - offset
        last_part_cut = (end % TG_CHUNK) + 1
        part_count = math.ceil(end / TG_CHUNK) - math.floor(offset / TG_CHUNK)

        # --- HEADERS ---
        content_length = end - start + 1
        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'attachment; filename="{file_name}"; filename*=UTF-8\'\'{encoded_file_name}',
            "Content-Length": str(content_length),
        }
        headers.update(cors_headers())

        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        # --- START STREAMING ---
        # আমরা সরাসরি custom_dl কল না করে আমাদের 'yield_with_retry' কল করব
        body = yield_with_retry(
            client=message._client, # ক্লাস্টার ক্লায়েন্ট পাস করা হচ্ছে
            message=message,
            file_id=file_id,
            chunk_index=chunk_index,
            first_part_cut=first_part_cut,
            last_part_cut=last_part_cut,
            part_count=part_count
        )

        return web.Response(status=status, body=body, headers=headers)

    except Exception as e:
        logging.error(f"Stream Helper Error: {e}")
        raise web.HTTPInternalServerError()
