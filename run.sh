#!/bin/bash

# Update Script (Optional for VPS, Skipped on Heroku often)
if [ -f "update.py" ]; then
    python3 update.py
fi

# Start the Bot Module
python3 -m bot
