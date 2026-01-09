import os
import sys
import logging
import asyncio
import random
import time
from pyrogram import Client, idle, enums
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

# --- 🕒 ACCESS TRACKING (IP LOGS) ---
ACCESS_LOGS = {}

# ⚡ TESTING TIME LIMIT: 2 Minutes (120 Seconds)
# পরে এটি বাড়িয়ে ৬ ঘণ্টা (21600) করে দেবেন
TIME_LIMIT = 120 

# --- 🔥 LOG TO CHANNEL FUNCTION ---
async def send_log(bot, text):
    try:
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"<b>⚠️ Server Log:</b>\n\n{text}",
                disable_web_page_preview=True
            )
    except Exception:
        pass

# --- 🧹 CLEANUP LOGS (RAM Saver) ---
async def cleanup_logs():
    """পুরানো লগ পরিষ্কার করবে"""
    current_time = time.time()
    # লিমিটের চেয়ে বেশি পুরোনো ডাটা ডিলিট
    expired = [k for k, v in ACCESS_LOGS.items() if current_time - v > TIME_LIMIT + 60]
    for k in expired:
        del ACCESS_LOGS[k]

# --- AUTO RESTART ---
async def auto_restart():
    logger.info("⏳ Scheduled Auto-Restart Triggered!")
    os.execl(sys.executable, sys.executable, *sys.argv)

# --- WEB SERVER ROUTES ---
routes = web.RouteTableDef()

@routes.get("/", allow_head=True)
async def root_route_handler(request):
    return web.json_response({
        "status": "Online", 
        "security": "2-Min Resume Limit", 
        "maintainer": "AnimeToki"
    })

# --- 🔥 SMART CLUSTER REQUEST PROCESSOR ---
async def process_request(request):
    try:
        file_id = request.match_info['file_id']

        # 🛡️ RESUME BLOCKER LOGIC (IP Check) 🛡️
        # ১. ইউজারের IP বের করা
        user_ip = request.headers.get("X-Forwarded-For") or request.remote or "Unknown"
        if "," in user_ip: 
            user_ip = user_ip.split(",")[0].strip()

        # ২. ইউনিক কী (IP + FileID)
        access_key = f"{user_ip}_{file_id}"
        current_time = time.time()

        # ৩. চেক করা
        if access_key in ACCESS_LOGS:
            start_time = ACCESS_LOGS[access_key]
            elapsed_time = current_time - start_time
            
            # যদি ২ মিনিটের বেশি হয় -> ব্লক 🚫
            if elapsed_time > TIME_LIMIT:
                return web.Response(
                    text=f"🚫 <b>Link Expired!</b>\nYour {int(TIME_LIMIT/60)} minutes download window has passed.\nYou cannot resume this file anymore.", 
                    status=403, 
                    content_type='text/html'
                )
        else:
            # নতুন ইউজার -> টাইম রেকর্ড করলাম ✅
            ACCESS_LOGS[access_key] = current_time

        # --- DATABASE & FILE LOGIC ---
        file_data = await db.get_file(file_id)
        
        if not file_data:
            return web.Response(text="❌ File Not Found!", status=404)
        
        db_file_name = file_data.get('file_name')
        locations = file_data.get('locations', [])
        
        if not locations and file_data.get('msg_id'):
            locations.append({'chat_id': Config.BIN_CHANNEL_1, 'message_id': file_data.get('msg_id')})

        # ১. সব বট লিস্ট
        all_clients = request.app['all_clients']
        random.shuffle(all_clients) 
        
        src_msg = None
        working_client = None

        # ২. ফাইল খোঁজা
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
                break 

        if not src_msg:
            return web.Response(text="❌ File Not Found! (Check Bot Admins)", status=410)

        # 🔥 DEBUG LOG
        try:
            bot_name = working_client.name if working_client else "Unknown"
            debug_text = f"🔍 **Limit Check:**\nServed via: `{bot_name}`\nIP: `{user_ip}`\nAllowed Time: `{TIME_LIMIT}s`"
            asyncio.create_task(send_log(request.app['bot'], debug_text))
            logger.info(f"🟢 Served by: {bot_name} | IP: {user_ip}")
        except Exception as e:
            logger.error(f"Debug Log Error: {e}")

        # ৪. সফল ক্লায়েন্ট দিয়ে ডাউনলোড শুরু (Retry Logic সহ)
        try:
            return await media_streamer(request, src_msg, custom_file_name=db_file_name)
        
        except FileReferenceExpired:
            logger.warning(f"⚠️ FileReferenceExpired for {db_file_name}. Refreshing...")
            try:
                refresh_msg = await working_client.get_messages(src_msg.chat.id, src_msg.id)
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

    # ১. মেইন সেশন
    if Config.SESSION_STRING:
        clients.append(Client(
            "MainBot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=Config.SESSION_STRING,
            plugins=dict(root="bot/plugins"), 
            in_memory=True,
            ipv6=False,
            workers=100, 
            sleep_threshold=60
        ))
        logger.info("✅ Main Session Loaded with Plugins!")

    # ২. মাল্টি সেশন
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

    app = web.Application(client_max_size=None)
    app.add_routes(routes)
    app['all_clients'] = clients
    app['bot'] = clients[0]

    logger.info(f"🚀 Starting Cluster with {len(clients)} Bots...")
    for c in clients:
        try:
            await c.start()
        except Exception as e:
            logger.error(f"❌ Boot Fail {c.name}: {e}")

    await send_log(clients[0], f"🚀 **System Started!**\nLimit: `2 Minutes`\nBots: `{len(clients)}`")

    asyncio.create_task(bandwidth_monitor())

    # Scheduler: Restart + Cleanup
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_restart, "interval", hours=4)
    scheduler.add_job(cleanup_logs, "interval", minutes=5) # প্রতি ৫ মিনিটে লগ ক্লিন করবে
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
