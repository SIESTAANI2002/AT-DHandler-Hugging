import os
import sys
import logging
import asyncio
import random
from pyrogram import Client, idle, enums
# 👇 এই লাইনটি নতুন যুক্ত করা হয়েছে (এরর ফিক্সের জন্য)
from pyrogram.errors import FileReferenceExpired 
from aiohttp import web
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Root Path Fix
sys.path.append(os.getcwd())

from bot.info import Config
from bot.utils.database import db
from bot.utils.stream_helper import media_streamer 
from bot.plugins.monitor import bandwidth_monitor

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# --- 🔥 LOG TO CHANNEL FUNCTION ---
async def send_log(bot, text):
    """Log Channel এ মেসেজ পাঠানোর ফাংশন"""
    try:
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"<b>⚠️ Server Log:</b>\n\n{text}",
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Failed to send log to channel: {e}")

# --- AUTO RESTART ---
async def auto_restart():
    logger.info("⏳ Scheduled Auto-Restart Triggered!")
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- WEB SERVER ROUTES ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({
        "status": "Cluster System Online", 
        "node": "Multi-Bot Farm", 
        "maintainer": "AnimeToki"
    })

# --- 🔥 SMART CLUSTER REQUEST PROCESSOR (Fixed FileRef Error) ---
async def process_request(request):
    try:
        file_id = request.match_info['file_id']
        file_data = await db.get_file(file_id)
        
        if not file_data:
            return web.Response(text="❌ File Not Found!", status=404)
        
        db_file_name = file_data.get('file_name')
        locations = file_data.get('locations', [])
        
        if not locations and file_data.get('msg_id'):
            locations.append({'chat_id': Config.BIN_CHANNEL_1, 'message_id': file_data.get('msg_id')})

        # ১. সব বট (Clients) লিস্ট নেওয়া
        all_clients = request.app['all_clients']
        
        # ২. লটারি করা (Shuffle) - যাতে লোড ব্যালেন্স হয়
        random.shuffle(all_clients) 
        
        src_msg = None
        working_client = None

        # ৩. একটার পর একটা বট দিয়ে ট্রাই করা (Cluster Power)
        for client in all_clients:
            for loc in locations:
                chat_id = loc.get('chat_id')
                msg_id = loc.get('message_id')
                if not chat_id or not msg_id: continue
                
                try:
                    msg = await client.get_messages(chat_id, msg_id)
                    if msg and (msg.document or msg.video or msg.audio):
                        src_msg = msg
                        working_client = client
                        break 
                except Exception:
                    continue
            
            if src_msg:
                break # ফাইল পাওয়া গেছে

        if not src_msg:
            return web.Response(text="❌ File Not Found! (Check Bot Admins)", status=410)

        # 🔥 DEBUG LOG
        try:
            bot_name = working_client.name if working_client else "Unknown"
            debug_text = f"🔍 **Load Balance Check:**\nServed via: `{bot_name}`\nFile: `{db_file_name}`"
            asyncio.create_task(send_log(request.app['bot'], debug_text))
            logger.info(f"🟢 Served by: {bot_name}")
        except Exception as e:
            logger.error(f"Debug Log Error: {e}")

        # ৪. সফল ক্লায়েন্ট দিয়ে ডাউনলোড শুরু (With Retry Logic) 🛠️
        try:
            return await media_streamer(request, src_msg, custom_file_name=db_file_name)
        
        except FileReferenceExpired:
            # ⚠️ যদি রেফারেন্স এক্সপায়ার হয়, লগ করে রিফ্রেশ করব
            logger.warning(f"⚠️ FileReferenceExpired for {db_file_name}. Refreshing...")
            
            try:
                # ফোর্স রিফ্রেশ (আবার মেসেজ ফেচ করা)
                refresh_msg = await working_client.get_messages(src_msg.chat.id, src_msg.id)
                
                # আবার স্ট্রিম করার চেষ্টা
                return await media_streamer(request, refresh_msg, custom_file_name=db_file_name)
            except Exception as e:
                logger.error(f"❌ Refresh Failed: {e}")
                return web.Response(text="❌ File Refresh Failed! Try again later.", status=500)

    except Exception as e:
        if request.app.get('bot'):
            await send_log(request.app['bot'], f"❌ Stream Error:\n`{str(e)}`")
        logger.error(f"Server Error: {e}")
        return web.Response(text=f"Server Error: {e}", status=500)

@routes.get("/stream/{file_id}")
async def stream_route_handler(request): return await process_request(request)

@routes.get("/watch/{file_id}")
async def watch_handler(request): return await process_request(request)

@routes.get("/dl/{file_id}")
async def download_handler(request): return await process_request(request)

# --- 🚀 CLUSTER STARTUP LOGIC ---
async def start_streamer():
    clients = []

    # ১. মেইন সেশন লোড (With Plugins ✅)
    if Config.SESSION_STRING:
        clients.append(Client(
            "MainBot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=Config.SESSION_STRING,
            plugins=dict(root="bot/plugins"), # 👈 MainBot Plugins Enabled
            in_memory=True,
            ipv6=False,
            workers=100, 
            sleep_threshold=60
        ))
        logger.info("✅ Main Session Loaded with Plugins!")

    # ২. মাল্টি সেশন লোড (No Plugins ❌)
    multi_sessions = getattr(Config, "MULTI_SESSIONS", [])
    
    if multi_sessions:
        for i, session in enumerate(multi_sessions):
            try:
                clients.append(Client(
                    f"ClusterBot_{i+1}",
                    api_id=Config.API_ID,
                    api_hash=Config.API_HASH,
                    session_string=session,
                    in_memory=True,
                    ipv6=False,
                    workers=100,
                    sleep_threshold=60
                ))
                logger.info(f"✅ Cluster Bot {i+1} Added!")
            except Exception as e:
                logger.error(f"❌ Failed to load Cluster Bot {i+1}: {e}")

    if not clients:
        logger.error("❌ No Bots Found! Add SESSION_STRING.")
        return

    # অ্যাপ সেটআপ
    app = web.Application(client_max_size=None)
    app.add_routes(routes)
    app['all_clients'] = clients
    app['bot'] = clients[0]

    # সব স্টার্ট করা
    logger.info(f"🚀 Starting Cluster with {len(clients)} Bots...")
    for c in clients:
        try:
            await c.start()
        except Exception as e:
            logger.error(f"❌ Boot Fail {c.name}: {e}")

    await send_log(clients[0], f"🚀 **Cluster System Started!**\n\n🔹 Total Bots: `{len(clients)}`\n🔹 Plugins: `Enabled (MainBot)`\n🔹 Debug Log: `ON`\n🔹 URL: `{Config.URL}`")

    asyncio.create_task(bandwidth_monitor())

    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_restart, "interval", hours=4)
    scheduler.start()

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, Config.BIND_ADRESS, Config.PORT).start()
    
    logger.info(f"🌐 Cluster Server Running at: {Config.URL}")
    
    await idle()
    
    for c in clients: 
        if c.is_connected:
            await c.stop()

if __name__ == "__main__":
    try:
        asyncio.run(start_streamer())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by User")
