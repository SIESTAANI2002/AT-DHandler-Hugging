from aiohttp import web
from bot.info import Config
from bot.utils.database import db
from bot.utils.stream_helper import media_streamer, cors_headers

routes = web.RouteTableDef()

# ======================================================
# DOWNLOAD ROUTE
# ======================================================
@routes.get("/dl/{id}", allow_head=True)
async def stream_handler(request):
    try:
        fid = request.match_info["id"]
        
        # ১. ডাটাবেস চেক
        file_data = await db.get_file(fid)
        if not file_data:
            return web.Response(text="❌ File not found in Database!", status=404)
        
        # ২. ইনফো লোড
        db_file_name = file_data.get('file_name')
        msg_id = int(file_data.get("msg_id"))
        chat_id = int(file_data.get("chat_id", Config.BIN_CHANNEL_1))
        
        # ৩. মেসেজ আনা
        bot = request.app['bot']
        try:
            msg = await bot.get_messages(chat_id, msg_id)
        except:
            return web.Response(text="❌ File Message Deleted!", status=404)

        if not msg:
             return web.Response(text="❌ File Message not found!", status=404)

        # ৪. সবকিছু Stream Helper এর কাছে পাঠিয়ে দেওয়া
        return await media_streamer(request, msg, custom_file_name=db_file_name)

    except Exception as e:
        return web.Response(text=f"❌ Server Error: {e}", status=500)

# ======================================================
# WATCH ROUTE (Simple Player)
# ======================================================
@routes.get("/watch/{id}", allow_head=True)
async def watch_handler(request):
    fid = request.match_info["id"]
    dl_url = f"/dl/{fid}"

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Watch Video</title>
        <style>
            body {{ margin: 0; background: #000; height: 100vh; display: flex; justify-content: center; align-items: center; }}
            video {{ width: 100%; height: 100%; object-fit: contain; }}
        </style>
    </head>
    <body>
        <video controls autoplay playsinline preload="auto">
            <source src="{dl_url}" type="video/mp4">
        </video>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html", headers=cors_headers())

# ======================================================
# ROOT & OPTIONS
# ======================================================
@routes.get("/")
async def root(request):
    return web.json_response({"status": "running"}, headers=cors_headers())

async def options_handler(request):
    return web.Response(status=204, headers=cors_headers())
