import os
import logging
from os import environ
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv('config.env')

UPSTREAM_REPO = environ.get('UPSTREAM_REPO', "")
UPSTREAM_BRANCH = environ.get('UPSTREAM_BRANCH', "main")

if UPSTREAM_REPO:
    if os.path.exists('.git'):
        os.system("rm -rf .git")
    
    update_cmd = f"git init -q && git config --global user.email 'bot@updates.com' && git config --global user.name 'Bot' && git remote add origin {UPSTREAM_REPO} && git fetch origin -q && git reset --hard origin/{UPSTREAM_BRANCH} -q"

    logging.info(f"🔄 Checking updates from: {UPSTREAM_REPO}")
    try:
        os.system(update_cmd)
        logging.info("✅ Update Completed!")
    except Exception as e:
        logging.error(f"❌ Update Failed: {e}")
