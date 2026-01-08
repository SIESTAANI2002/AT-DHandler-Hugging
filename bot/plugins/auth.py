from pyrogram import Client, filters
from pyrogram.types import Message
from bot.info import Config
from bot.utils.database import db

# --- 🔐 AUTHORIZE USER (/add) ---
@Client.on_message(filters.command("add") & filters.user(Config.OWNER_ID))
async def authorize_user(bot: Client, message: Message):
    user_id = None
    
    # ১. যদি রিপ্লাই করে কমান্ড দেয়
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    
    # ২. যদি আইডিসহ কমান্ড দেয় (যেমন: /add 123456)
    elif len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            return await message.reply("❌ Invalid User ID! Please provide a number.")
    
    if not user_id:
        return await message.reply("⚠️ Give a User ID or Reply to a User.\nExample: `/add 123456`")

    try:
        # ডাটাবেসে অ্যাড করা (আপনার db.add_auth_user ব্যবহার করে)
        await db.add_auth_user(user_id)
        await message.reply(f"✅ User `{user_id}` has been **Authorized** successfully!")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# --- ⛔ REVOKE USER (/remove) ---
@Client.on_message(filters.command("remove") & filters.user(Config.OWNER_ID))
async def unauthorize_user(bot: Client, message: Message):
    user_id = None
    
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif len(message.command) == 2:
        try:
            user_id = int(message.command[1])
        except ValueError:
            return await message.reply("❌ Invalid User ID!")
            
    if not user_id:
        return await message.reply("⚠️ Give a User ID or Reply to a User.\nExample: `/remove 123456`")

    try:
        # ডাটাবেস থেকে রিমুভ করা
        await db.remove_auth_user(user_id)
        await message.reply(f"🚫 User `{user_id}` access has been **Revoked**!")
    except Exception as e:
        await message.reply(f"❌ Error: {e}")

# --- 📜 LIST AUTHORIZED USERS (/users) ---
@Client.on_message(filters.command("users") & filters.user(Config.OWNER_ID))
async def list_authorized_users(bot: Client, message: Message):
    try:
        # আপনার DB ফাংশন শুধু আইডি-র লিস্ট রিটার্ন করে [123, 456]
        users_list = await db.get_auth_users()
        
        if not users_list:
            return await message.reply("📂 No Authorized Users found!")
        
        text = f"<b>🔐 Authorized Users List ({len(users_list)}):</b>\n\n"
        
        for i, user_id in enumerate(users_list, 1):
            # ইউজার আইডির মেনশন লিঙ্ক তৈরি
            text += f"{i}. <code>{user_id}</code>\n"
            
        await message.reply(text)
        
    except Exception as e:
        await message.reply(f"❌ Error fetching users: {e}")
