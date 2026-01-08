import motor.motor_asyncio
import datetime
from bot.info import Config
from pyrogram.types import Message

class Database:
    def __init__(self, uri, database_name):
        self._client = motor.motor_asyncio.AsyncIOMotorClient(uri)
        self.db = self._client[database_name]
        self.col = self.db[Config.COLLECTION_NAME]
        self.config_col = self.db['bot_settings'] 

    def new_user(self, id):
        return dict(
            id=id,
            join_date=datetime.date.today().isoformat()
        )

    # --- 🔥 ADD FILE (Global) ---
    async def add_file(self, media_msg: Message, file_id: str, unique_id: str):
        media = getattr(media_msg, media_msg.media.value)
        file_name = getattr(media, 'file_name', 'Unknown')
        file_size = getattr(media, 'file_size', 0)
        mime_type = getattr(media, 'mime_type', 'None')
        caption = media_msg.caption or ""

        await self.col.update_one(
            {'_id': unique_id},
            {
                '$set': {
                    'file_id': file_id,
                    'file_name': file_name,
                    'file_size': file_size,
                    'mime_type': mime_type,
                    'caption': caption
                }
            },
            upsert=True
        )

        new_loc = {'chat_id': media_msg.chat.id, 'message_id': media_msg.id}
        await self.col.update_one(
            {'_id': unique_id},
            {'$addToSet': {'locations': new_loc}}
        )

    async def get_file(self, unique_id: str):
        return await self.col.find_one({'_id': unique_id})

    async def get_total_files_count(self):
        return await self.col.count_documents({})

    # --- 📊 MAIN BOT BANDWIDTH (Heroku) ---
    # এই ফাংশনগুলো মেইন বটের জন্য (যা আগে থেকেই ছিল)
    
    async def add_bandwidth(self, upload_bytes, download_bytes):
        await self.config_col.update_one(
            {'_id': 'bandwidth_stats'},
            {'$inc': {'total_upload': upload_bytes, 'total_download': download_bytes}},
            upsert=True
        )

    async def get_bandwidth(self):
        data = await self.config_col.find_one({'_id': 'bandwidth_stats'})
        if not data:
            return 0, 0
        return data.get('total_upload', 0), data.get('total_download', 0)

    async def check_monthly_reset(self):
        now = datetime.datetime.now()
        current_month = f"{now.year}-{now.month}" 
        data = await self.config_col.find_one({'_id': 'bandwidth_stats'})
        
        if not data:
            await self.config_col.update_one(
                {'_id': 'bandwidth_stats'},
                {'$set': {'last_reset': current_month, 'total_upload': 0, 'total_download': 0}},
                upsert=True
            )
            return

        if data.get('last_reset') != current_month:
            await self.config_col.update_one(
                {'_id': 'bandwidth_stats'},
                {'$set': {'total_upload': 0, 'total_download': 0, 'last_reset': current_month}}
            )

    # --- 🚀 STREAMER BANDWIDTH (Oracle - New Functions) ---
    # এখানে আমরা আলাদা ID 'streamer_bandwidth' ব্যবহার করছি
    
    async def add_streamer_bandwidth(self, upload, download):
        await self.config_col.update_one(
            {'_id': 'streamer_bandwidth'},
            {'$inc': {'upload': upload, 'download': download}},
            upsert=True
        )

    async def get_streamer_bandwidth(self):
        data = await self.config_col.find_one({'_id': 'streamer_bandwidth'})
        if not data:
            return 0, 0
        return data.get('upload', 0), data.get('download', 0)

    async def check_streamer_reset(self):
        now = datetime.datetime.now()
        current_month = f"{now.year}-{now.month}" 
        data = await self.config_col.find_one({'_id': 'streamer_bandwidth'})
        
        if not data:
            await self.config_col.update_one(
                {'_id': 'streamer_bandwidth'},
                {'$set': {'last_reset': current_month, 'upload': 0, 'download': 0}},
                upsert=True
            )
            return

        if data.get('last_reset') != current_month:
            await self.config_col.update_one(
                {'_id': 'streamer_bandwidth'},
                {'$set': {'upload': 0, 'download': 0, 'last_reset': current_month}}
            )

    # --- 💾 TOTAL STORAGE ---
    async def get_total_storage(self):
        pipeline = [{"$group": {"_id": None, "total_size": {"$sum": "$file_size"}}}]
        cursor = self.col.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        total_bytes = result[0]['total_size'] if result else 0
        total_files = await self.col.count_documents({})
        return total_files, total_bytes

    # --- 🔐 AUTH SYSTEM ---
    async def add_auth_user(self, user_id):
        await self.config_col.update_one(
            {'_id': 'auth_list'},
            {'$addToSet': {'users': int(user_id)}},
            upsert=True
        )

    async def remove_auth_user(self, user_id):
        await self.config_col.update_one(
            {'_id': 'auth_list'},
            {'$pull': {'users': int(user_id)}}
        )

    async def get_auth_users(self):
        data = await self.config_col.find_one({'_id': 'auth_list'})
        return data['users'] if data and 'users' in data else []

    async def is_user_allowed(self, user_id):
        if user_id == Config.OWNER_ID:
            return True
        data = await self.config_col.find_one({'_id': 'auth_list'})
        if data and 'users' in data:
            return int(user_id) in data['users']
        return False

# Initialize Database
db = Database(Config.DATABASE_URL, Config.DATABASE_NAME)
