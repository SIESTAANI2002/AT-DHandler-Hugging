import os
from os import environ
from dotenv import load_dotenv

# Load config.env if exists
if os.path.exists('config.env'):
    load_dotenv('config.env')
    

class Config:
    # --- 🤖 NEW BOT INFO ---
    API_ID = int(environ.get("API_ID", "123456"))
    API_HASH = environ.get("API_HASH", "abcd")
    BOT_TOKEN = environ.get("BOT_TOKEN", "") # নতুন বটের টোকেন

    # --- 🗄️ SAME DATABASE (Main Bot এরটা দেবেন) ---
    DATABASE_URL = environ.get("DATABASE_URL", "") 
    DATABASE_NAME = environ.get("DATABASE_NAME", "AnimeToki")
    COLLECTION_NAME = environ.get("COLLECTION_NAME", "Telegram_Files")

    # --- 📦 SAME BIN CHANNELS (এই বটকেও অ্যাডমিন বানাতে হবে) ---
    BIN_CHANNEL_1 = int(environ.get("BIN_CHANNEL_1", "0"))
    BIN_CHANNEL_2 = int(environ.get("BIN_CHANNEL_2", "0"))
    BIN_CHANNEL_3 = int(environ.get("BIN_CHANNEL_3", "0"))
    BIN_CHANNEL_4 = int(environ.get("BIN_CHANNEL_4", "0"))
    LOG_CHANNEL = int(environ.get("LOG_CHANNEL", "0"))

    # --- 🌐 NEW BOT URL ---
    # এই বটের লিংক (যেমন: https://streamer-bot.herokuapp.com)
    URL = environ.get("URL", "") 
    PORT = int(environ.get("PORT", "8080"))
    BIND_ADRESS = "0.0.0.0"
    
    # OWNER ID
    OWNER_ID = int(environ.get("OWNER_ID", "0"))
