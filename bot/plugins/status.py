import time
import psutil
from pyrogram import Client, filters
from bot.utils.database import db
from bot.utils.human_readable import humanbytes
from bot.info import Config

BOT_START_TIME = time.time()

def get_readable_time(seconds):
    result = ""
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0: result += f"{days}d "
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0: result += f"{hours}h "
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0: result += f"{minutes}m "
    seconds = int(seconds)
    result += f"{seconds}s"
    return result

@Client.on_message(filters.command(["stats", "status"]) & filters.user(Config.OWNER_ID))
async def stats_handler(bot, message):
    msg = await message.reply("🔄 **Fetching Stats...**", quote=True)
    
    # System Stats
    cpu_per = psutil.cpu_percent()
    cpu_count = psutil.cpu_count()
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    
    # Telegram Cloud Storage
    total_files, total_bytes = await db.get_total_storage()
    
    # 🔥 ORACLE BANDWIDTH (Persistent DB Data)
    ul_bytes, dl_bytes = await db.get_streamer_bandwidth()
    
    server_upload = humanbytes(ul_bytes)
    server_download = humanbytes(dl_bytes)
    uptime = get_readable_time(time.time() - BOT_START_TIME)

    stats_text = (
        f"🤖 **Streamer (Oracle) Stats**\n\n"
        f"⏳ **Uptime:** `{uptime}`\n"
        f"💻 **CPU:** `{cpu_per}%` | **RAM:** `{mem.percent}%`\n"
        f"💾 **Disk:** `{humanbytes(disk.free)}` Free\n\n"

        f"☁️ **Telegram Cloud:** `{total_files}` Files\n\n"

        f"📡 **Traffic (Monthly):**\n"
        f"⬆️ **Streamed:** `{server_upload}`\n"
        f"⬇️ **Download:** `{server_download}`"
    )
    
    await msg.edit(stats_text)
