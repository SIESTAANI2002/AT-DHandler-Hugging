import os
import sys
import asyncio
from pyrogram import Client, filters
from bot.info import Config

@Client.on_message(filters.command("restart") & filters.user(Config.OWNER_ID))
async def restart_handler(bot, message):
    # ১. প্রথমে মেসেজ দেওয়া
    msg = await message.reply_text("🔄 **Streamer Server Restarting...**", quote=True)
    
    # ২. ফাইল সেভ করা (Force Write)
    restart_file = os.path.join(os.getcwd(), ".restartmsg")
    
    with open(restart_file, "w") as f:
        f.write(f"{msg.chat.id}\n{msg.id}")
        f.flush()               # বাফার মেমরি ক্লিয়ার করা
        os.fsync(f.fileno())    # ডিস্কে লেখা নিশ্চিত করা
    
    # ৩. মেসেজ আপডেট করা
    await msg.edit_text("🔄 **Rebooting...**")
    
    # ৪. ১ সেকেন্ড সময় দেওয়া (Telegram API Sync হওয়ার জন্য)
    await asyncio.sleep(1)
    
    # ৫. রিস্টার্ট কমান্ড
    os.execl(sys.executable, sys.executable, *sys.argv)
