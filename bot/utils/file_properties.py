from pyrogram import Client
from pyrogram.types import Message
from typing import Any

async def get_file_id_for_stream(media: Any):
    """
    যেকোনো মিডিয়া (Video, Document, Audio) থেকে File ID অবজেক্ট রিটার্ন করে।
    """
    # আমরা সরাসরি মিডিয়া অবজেক্ট রিটার্ন করছি কারণ পাইরোগ্রামে 
    # media.file_id এবং media.file_size থাকে।
    return media

def get_name(media: Any) -> str:
    """
    মিডিয়া থেকে ফাইলের নাম বের করার চেষ্টা করে।
    """
    if hasattr(media, "file_name"):
        return media.file_name
    return "Unknown_File"
