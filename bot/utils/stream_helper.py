import math
import logging
from aiohttp import web
from urllib.parse import quote 
from bot.utils.custom_dl import ByteStreamer
from bot.utils.file_properties import get_file_id_for_stream

TG_CHUNK = 1024 * 1024  # 1MB Telegram Chunk Size

# CORS Headers
def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range, Content-Type, User-Agent",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range",
    }

async def media_streamer(request, message, custom_file_name=None):
    try:
        media = message.video or message.document or message.audio or message.animation
        if not media:
            raise web.HTTPNotFound(text="Media not found")

        # ফাইল প্রপার্টিজ নেওয়া
        file_id = await get_file_id_for_stream(media)
        file_size = file_id.file_size

        # --- FILENAME LOGIC ---
        if custom_file_name:
            file_name = custom_file_name
        else:
            file_name = getattr(media, "file_name", None)
            if not file_name:
                file_name = f"AnimeToki_{message.id}.mp4"

        encoded_file_name = quote(file_name)
        mime_type = getattr(media, "mime_type", "video/mp4") or "video/mp4"

        # --- RANGE HEADER HANDLING (Resume Support) ---
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
            return web.Response(
                status=416, 
                headers={"Content-Range": f"bytes */{file_size}"}
            )

        # --- OFFSET CALCULATION (FileStreamBot Magic) ---
        # 1. টেলিগ্রামের জন্য Offset অবশ্যই 1MB এর গুণিতক হতে হবে
        offset = start - (start % TG_CHUNK) 
        
        # 2. পাইরোগ্রামে পাঠানোর জন্য Chunk Index বের করা
        chunk_index = offset // TG_CHUNK
        
        # 3. প্রথম চাঙ্ক থেকে কতটুকু কেটে ফেলতে হবে
        first_part_cut = start - offset
        
        # 4. শেষ চাঙ্ক কোথায় থামবে
        last_part_cut = (end % TG_CHUNK) + 1
        
        # 5. মোট কতগুলো চাঙ্ক নামাতে হবে
        part_count = math.ceil(end / TG_CHUNK) - math.floor(offset / TG_CHUNK)

        # --- STREAMING START ---
        bot = request.app['bot']
        streamer = ByteStreamer(bot)
        
        body = streamer.yield_file(
            media.file_id,
            chunk_index,
            first_part_cut,
            last_part_cut,
            part_count,
        )

        headers = {
            "Content-Type": mime_type,
            "Accept-Ranges": "bytes",
            "Content-Disposition": f'attachment; filename="{file_name}"; filename*=UTF-8\'\'{encoded_file_name}',
            "Content-Length": str(end - start + 1),
        }
        headers.update(cors_headers())

        if status == 206:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

        return web.Response(status=status, body=body, headers=headers)

    except Exception as e:
        logging.error(f"Stream Helper Error: {e}")
        raise web.HTTPInternalServerError()
