from pyrogram import Client, filters
from bot.info import Config
from bot.utils.database import db

# group=-1 দেওয়ার মানে হলো, এই ফাইলটি সবার আগে রান হবে।
# যদি ইউজার অথরাইজড না হয়, তাহলে এখানেই আটকে দেবে।
@Client.on_message(filters.private, group=-1)
async def auth_gatekeeper(bot, message):
    user_id = message.from_user.id

    # ১. Owner চেক (মালিকের সব মাফ)
    if user_id == Config.OWNER_ID:
        return  # পাস করে দাও (পরের কোড কাজ করবে)

    # ২. Database চেক (অথরাইজড ইউজার কি না)
    if await db.is_user_allowed(user_id):
        return  # পাস করে দাও

    # ৩. যদি অথরাইজড না হয় -> ব্লক মেসেজ
    await message.reply_text(
        "🚫 **Access Denied!**\n\n"
        "This is a **Private Streamer Bot**.\n"
        "Only Authorized Users can access files.\n"
        "🔐 Contact the Owner for permission.",
        quote=True
    )
    
    # 🛑 STOP: অন্য কোনো কমান্ড (start, dl) আর কাজ করবে না
    message.stop_propagation()
