import os
import sys
import logging
import asyncio
import random
from pyrogram import Client, idle
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

# --- 🛠️ HELPER: File Size Formatter (API এর জন্য দরকার) ---
def humanbytes(size):
    if not size: return ""
    power = 2**10
    n = 0
    dic_powerN = {0: ' ', 1: 'Ki', 2: 'Mi', 3: 'Gi', 4: 'Ti'}
    while size > power:
        size /= power
        n += 1
    return str(round(size, 2)) + " " + dic_powerN[n] + 'B'

# --- 🔥 LOG FUNCTION ---
async def send_log(bot, text):
    try:
        if Config.LOG_CHANNEL:
            await bot.send_message(
                chat_id=int(Config.LOG_CHANNEL),
                text=f"<b>⚠️ Server Log:</b>\n\n{text}",
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.warning(f"Log Error: {e}")

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
        "mode": "API + Quiet High Speed", 
        "maintainer": "AnimeToki"
    })

# --- 🟡 API ROUTE (Frontend এর জন্য JSON Data) ---
@routes.get("/api/file/{file_id}")
async def api_file_handler(request):
    try:
        file_id = request.match_info['file_id']
        file_data = await db.get_file(file_id)
        
        if not file_data:
            return web.json_response(
                {"error": True, "message": "Not Found"}, 
                headers={"Access-Control-Allow-Origin": "*"}
            )
        
        f_name = file_data.get('file_name', 'Unknown File')
        f_size = "Unknown"
        
        # সাইজ ফরম্যাট করা
        if file_data.get('file_size'):
             f_size = humanbytes(int(file_data.get('file_size')))
        
        # JSON রেসপন্স
        return web.json_response({
            "error": False,
            "file_name": f_name,
            "file_size": f_size
        }, headers={"Access-Control-Allow-Origin": "*"}) # CORS Header
        
    except Exception as e:
        return web.json_response(
            {"error": True, "message": str(e)}, 
            headers={"Access-Control-Allow-Origin": "*"}
        )

# --- 🔥 REQUEST PROCESSOR (Streaming) ---
async def process_request(request):
    try:
        file_id = request.match_info['file_id']
        
        # 🔥 ১. URL থেকে কাস্টম নাম চেক করা (Frontend থেকে আসলে)
        custom_name = request.query.get('name')

        # 2. Get File from Database
        file_data = await db.get_file(file_id)
        if not file_data:
            return web.Response(text="❌ File Not Found!", status=404)
        
        # 🔥 নাম সেট করা: যদি URL-এ নাম থাকে, সেটা ব্যবহার হবে
        if custom_name:
            db_file_name = custom_name
        else:
            db_file_name = file_data.get('file_name')

        locations = file_data.get('locations', [])
        
        if not locations and file_data.get('msg_id'):
            locations.append({'chat_id': Config.BIN_CHANNEL_1, 'message_id': file_data.get('msg_id')})

        # 3. Cluster Load Balancing
        all_clients = request.app['all_clients']
        random.shuffle(all_clients) 
        
        src_msg = None
        working_client = None

        # 4. File Hunting
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

        if not src_msg:
            return web.Response(text="❌ File Not Found! (Check Bot Admins)", status=410)

        # ❌ Access Log Removed (Quiet Mode)

        # 5. Streaming (With Error Fix)
        try:
            return await media_streamer(request, src_msg, custom_file_name=db_file_name)
        
        except FileReferenceExpired:
            logger.warning(f"⚠️ FileRef Expired. Refreshing...")
            try:
                refresh_msg = await working_client.get_messages(src_msg.chat.id, src_msg.id)
                return await media_streamer(request, refresh_msg, custom_file_name=db_file_name)
            except Exception as e:
                logger.error(f"❌ Refresh Failed: {e}")
                # শুধু রিফ্রেশ এরর হলে লগে পাঠাবে
                if request.app.get('bot'):
                    asyncio.create_task(send_log(request.app['bot'], f"❌ **Refresh Failed:**\n`{db_file_name}`\nError: `{e}`"))
                return web.Response(text="❌ Refresh Failed! Try again later.", status=500)

    except Exception as e:
        # 📢 SEND ERROR LOG (ONLY IF SERVER ERROR)
        if request.app.get('bot'):
            asyncio.create_task(send_log(request.app['bot'], f"❌ **Stream Error:**\n`{str(e)}`"))
            
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

    # Main Bot
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

    # Cluster Bots
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
        try: await c.start()
        except: pass

    # 📢 SEND STARTUP LOG (System Ready Message)
    await send_log(clients[0], f"🚀 **System Started!**\nMode: `API + Quiet Speed`\nBots: `{len(clients)}`")

    # Bandwidth Monitor & Auto Restart
    asyncio.create_task(bandwidth_monitor())
    scheduler = AsyncIOScheduler()
    scheduler.add_job(auto_restart, "interval", hours=4)
    scheduler.start()

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, Config.BIND_ADRESS, Config.PORT).start()
    
    logger.info(f"🌐 Server Running at: {Config.URL}")
    
    await idle()
    
    for c in clients: 
        if c.is_connected: await c.stop()

if __name__ == "__main__":
    try:
        asyncio.run(start_streamer())
    except KeyboardInterrupt:
        logger.info("🛑 Stopped by User")
