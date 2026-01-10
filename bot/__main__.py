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

# --- 🕒 ACCESS TRACKING ---
ACCESS_LOGS = {}

# ⚡ VALIDITY: ২ মিনিট ডাউনলোড উইন্ডো
TIME_LIMIT = 120  

# 🔒 SESSION TIMEOUT: ১০ মিনিট
# ২ মিনিট শেষ হওয়ার পর, আরও ৮ মিনিট ইউজার পুরোপুরি ব্লক থাকবে।
# IDM যাতে বারবার রিকোয়েস্ট পাঠিয়ে বাইপাস না করতে পারে।
SESSION_DURATION = 300 

# --- 🔥 LOG TO CHANNEL ---
async def send_log(bot, text):
    try:
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"<b>⚠️ Server Log:</b>\n\n{text}",
                disable_web_page_preview=True
            )
    except Exception: pass

# --- 🧹 CLEANUP LOGS ---
async def cleanup_logs():
    """মেমোরি ক্লিয়ার করে, কিন্তু ব্লক পিরিয়ড শেষ হওয়ার পর"""
    current_time = time.time()
    # যারা ১০ মিনিটের বেশি সময় আগে এসেছিল, শুধু তাদের লগ মুছবে
    expired = [k for k, v in ACCESS_LOGS.items() if current_time - v > SESSION_DURATION]
    for k in expired:
        del ACCESS_LOGS[k]
    
    if expired:
        logger.info(f"🧹 Cleaned {len(expired)} expired sessions.")

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
        "security": "Strict One-Time Session", 
        "maintainer": "AnimeToki"
    })

# --- 🔥 SMART CLUSTER REQUEST PROCESSOR ---
async def process_request(request):
    try:
        file_id = request.match_info['file_id']

        # 🛡️ IRON-CLAD SECURITY LOGIC 🛡️
        user_ip = request.headers.get("X-Forwarded-For") or request.remote or "Unknown"
        if "," in user_ip: user_ip = user_ip.split(",")[0].strip()

        access_key = f"{user_ip}_{file_id}"
        current_time = time.time()

        # ডিবাগিংয়ের জন্য রেঞ্জ হেডার চেক (লজিকের জন্য নয়)
        range_header = request.headers.get("Range")
        
        # --- লজিক শুরু ---
        if access_key in ACCESS_LOGS:
            # ইউজার আগে এসেছিল। চেক করব কতক্ষণ আগে।
            start_time = ACCESS_LOGS[access_key]
            elapsed_time = current_time - start_time
            
            # যদি ২ মিনিট (TIME_LIMIT) পার হয়ে যায়
            if elapsed_time > TIME_LIMIT:
                # ⛔ STRICT BLOCK: এখানে কোনো 'if is_resume' চেক নেই।
                # সময় শেষ মানেই শেষ। IDM নতুন রিকোয়েস্ট পাঠালেও ব্লক খাবে।
                
                wait_time = SESSION_DURATION - elapsed_time
                wait_msg = f"Try again in {int(wait_time/60)} mins." if wait_time > 0 else "Try again shortly."

                logger.info(f"🚫 Blocked (Time Up): IP={user_ip} | Elapsed={int(elapsed_time)}s")
                
                return web.Response(
                    text=f"🚫 <b>Link Expired!</b>\nYour 2-minute download window is over.<br>You cannot resume or restart immediately.<br><br><b>{wait_msg}</b>", 
                    status=403, 
                    content_type='text/html'
                )
            
            # সময় ২ মিনিটের কম? তাহলে ডাউনলোড বা রিজিউম করতে দাও।
            # আমরা এখানে টাইমার আপডেট করছি না! (NO RESET)
        
        else:
            # --- নতুন ইউজার ---
            # প্রথমবার এলো, তাই টাইমার সেট করলাম।
            # এই টাইমার আর আপডেট হবে না যতক্ষণ না লগ ডিলিট হয় (১০ মিনিট পর)।
            ACCESS_LOGS[access_key] = current_time
            logger.info(f"✅ New Session Started: IP={user_ip}")

        # --- DATABASE & FILE LOGIC ---
        file_data = await db.get_file(file_id)
        if not file_data: return web.Response(text="❌ File Not Found!", status=404)
        
        db_file_name = file_data.get('file_name')
        locations = file_data.get('locations', [])
        
        if not locations and file_data.get('msg_id'):
            locations.append({'chat_id': Config.BIN_CHANNEL_1, 'message_id': file_data.get('msg_id')})

        all_clients = request.app['all_clients']
        random.shuffle(all_clients) 
        
        src_msg = None
        working_client = None

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
                except: continue
            if src_msg: break 

        if not src_msg: return web.Response(text="❌ File Not Found!", status=410)

        # Streaming Headers to prevent caching
        headers = {
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }

        try:
            # মূল স্ট্রিমিং কল
            response = await media_streamer(request, src_msg, custom_file_name=db_file_name)
            # রেসপন্সে নো-ক্যাশ হেডার যোগ করা (যাতে ব্রাউজার চালাকি না করে)
            response.headers.update(headers)
            return response

        except FileReferenceExpired:
            logger.warning(f"⚠️ FileRef Expired. Refreshing...")
            try:
                refresh_msg = await working_client.get_messages(src_msg.chat.id, src_msg.id)
                response = await media_streamer(request, refresh_msg, custom_file_name=db_file_name)
                response.headers.update(headers)
                return response
            except Exception as e:
                logger.error(f"❌ Refresh Failed: {e}")
                return web.Response(text="❌ Refresh Failed!", status=500)

    except Exception as e:
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
        logger.info("✅ Main Session Loaded!")

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
            except: pass

    if not clients:
        logger.error("❌ No Bots Found!")
        return

    app = web.Application(client_max_size=None)
    app.add_routes(routes)
    app['all_clients'] = clients
    app['bot'] = clients[0]

    logger.info(f"🚀 Starting Cluster...")
    for c in clients:
        try: await c.start()
        except: pass

    await send_log(clients[0], f"🚀 **System Started!**\nTime Limit: {int(TIME_LIMIT/60)} Mins")

    asyncio.create_task(bandwidth_monitor())

    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_restart, "interval", hours=4)
    # Cleanup: প্রতি ১ মিনিটে চেক করবে ১০ মিনিট পুরনো লগ আছে কিনা
    scheduler.add_job(cleanup_logs, "interval", seconds=60) 
    scheduler.start()

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, Config.BIND_ADRESS, Config.PORT).start()
    
    logger.info(f"🌐 Running: {Config.URL}")
    await idle()
    for c in clients: 
        if c.is_connected: await c.stop()

if __name__ == "__main__":
    try:
        asyncio.run(start_streamer())
    except KeyboardInterrupt: pass
