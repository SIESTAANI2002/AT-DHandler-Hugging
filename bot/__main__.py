import os
import sys
import logging
import asyncio
import random

# Root Path Fix
sys.path.append(os.getcwd())

from pyrogram import Client, idle
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler # Scheduler Import
from bot.info import Config
from bot.utils.database import db
from bot.utils.stream_helper import media_streamer 
from bot.utils.human_readable import humanbytes 
from bot.plugins.monitor import bandwidth_monitor

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- 🔥 AUTO RESTART FUNCTION 🔥 ---
async def auto_restart():
    logger.info("⏳ Scheduled Auto-Restart Triggered!")
    # রিস্টার্ট করার আগে বাফার ক্লিন করা
    sys.stdout.flush()
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- 🌐 WEB SERVER ROUTES ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({"status": "Streamer Online", "node": "Oracle/VPS", "maintainer": "AnimeToki"})

# --- 🌍 API FOR EXTERNAL WEBSITE 🌍 ---
@routes.get("/api/file/{unique_id}")
async def file_api_handler(request):
    try:
        unique_id = request.match_info['unique_id']
        file_data = await db.get_file(unique_id)
        
        if not file_data:
            return web.json_response({"error": "File not found"}, status=404, headers={"Access-Control-Allow-Origin": "*"})

        file_name = file_data.get('file_name', 'Unknown File')
        file_size_bytes = int(file_data.get('file_size', 0))
        file_size = humanbytes(file_size_bytes)
        
        stream_link = f"{Config.URL}/stream/{unique_id}"
        
        response_data = {
            "file_name": file_name,
            "file_size": file_size,
            "download_link": stream_link,
            "stream_link": stream_link,
        }
        
        return web.json_response(
            response_data,
            headers={
                "Access-Control-Allow-Origin": "*", 
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        )
    except Exception as e:
        logger.error(f"API Error: {e}")
        return web.json_response({"error": str(e)}, status=500, headers={"Access-Control-Allow-Origin": "*"})

# --- 🔥 MAIN REQUEST PROCESSOR 🔥 ---
async def process_request(request):
    try:
        file_id = request.match_info['file_id']
        file_data = await db.get_file(file_id)
        
        if not file_data:
            return web.Response(text="❌ File Not Found in Database!", status=404)
        
        db_file_name = file_data.get('file_name')
        locations = file_data.get('locations', [])
        
        if not locations and file_data.get('msg_id'):
            locations.append({'chat_id': Config.BIN_CHANNEL_1, 'message_id': file_data.get('msg_id')})

        random.shuffle(locations)
        src_msg = None
        bot = request.app['bot']

        for loc in locations:
            chat_id = loc.get('chat_id')
            msg_id = loc.get('message_id')
            if not chat_id or not msg_id: continue
            try:
                msg = await bot.get_messages(chat_id, msg_id)
                if msg and (msg.document or msg.video or msg.audio):
                    src_msg = msg
                    break 
            except Exception as e:
                logger.warning(f"⚠️ Failed to fetch from {chat_id}: {e}")
                continue
        
        if not src_msg:
            return web.Response(text="❌ File Not Found in any Backup Channel!", status=410)

        return await media_streamer(request, src_msg, custom_file_name=db_file_name)

    except Exception as e:
        logger.error(f"Server Error: {e}")
        return web.Response(text=f"Server Error: {e}", status=500)

@routes.get("/stream/{file_id}")
async def stream_route_handler(request): return await process_request(request)

@routes.get("/watch/{file_id}")
async def watch_handler(request): return await process_request(request)

@routes.get("/dl/{file_id}")
async def download_handler(request): return await process_request(request)

# --- 🚀 BOT STARTUP LOGIC ---
async def start_streamer():
    bot = Client(
        "StreamerBot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN,
        plugins={"root": "bot.plugins"}, 
        workdir="session/",
        in_memory=True,
        sleep_threshold=300
    )

    app = web.Application(client_max_size=30000000)
    app.add_routes(routes)
    app['bot'] = bot

    logger.info("🚀 Starting Streamer Bot...")
    await bot.start()

    asyncio.create_task(bandwidth_monitor())
    logger.info("📊 Bandwidth Monitor Active.")

    # Restart Message Logic
    restart_file = os.path.join(os.getcwd(), ".restartmsg")
    if os.path.exists(restart_file):
        try:
            with open(restart_file, "r") as f:
                content = f.read().split()
                if len(content) == 2:
                    chat_id, msg_id = map(int, content)
                    await bot.edit_message_text(chat_id, msg_id, "✅ **Streamer Node Restarted Successfully!**")
            os.remove(restart_file)
        except Exception as e:
            logger.error(f"Restart Message Error: {e}")

    # --- ⏰ AUTO RESTART SCHEDULER (UPDATED) ---
    scheduler = AsyncIOScheduler()
    # hours=8 মানে প্রতি ৮ ঘণ্টায় একবার (24/8 = 3 times a day)
    scheduler.add_job(auto_restart, "interval", hours=8) 
    scheduler.start()
    logger.info("⏰ Auto-Restart Scheduled (Every 8 Hours)")

    # Channel Check
    target_channels = [Config.BIN_CHANNEL_1, Config.BIN_CHANNEL_2, Config.BIN_CHANNEL_3, Config.BIN_CHANNEL_4]
    for ch in target_channels:
        if ch and int(ch) != 0:
            try:
                await bot.get_chat(ch)
                logger.info(f"✅ Connected to Bin Channel: {ch}")
            except Exception as e:
                logger.error(f"❌ Error verifying channel {ch}: {e}")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, Config.BIND_ADRESS, Config.PORT)
    await site.start()
    
    logger.info(f"🌐 API & Streamer running at: {Config.URL}")
    
    await idle()
    await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(start_streamer())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by User")
