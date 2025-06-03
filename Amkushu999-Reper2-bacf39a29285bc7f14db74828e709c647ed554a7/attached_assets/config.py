import os
from dotenv import load_dotenv
import logging
import json

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot token for python-telegram-bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.error("Bot token is missing! Please set the BOT_TOKEN environment variable.")

# Telegram API credentials for Telethon
API_ID = os.getenv("API_ID", "")
API_HASH = os.getenv("API_HASH", "")
if not API_ID or not API_HASH:
    logger.error("API credentials are missing! Please set the API_ID and API_HASH environment variables.")

# User session string
USER_SESSION = os.getenv("USER_SESSION", "")
if not USER_SESSION:
    logger.error("User session is missing! Please set the USER_SESSION environment variable.")

# Source and destination channels
try:
    # Format: {"source_channels": [channel_id1, channel_id2, ...], "destination_channel": channel_id}
    CHANNEL_CONFIG = json.loads(os.getenv("CHANNEL_CONFIG", '{"source_channels": [], "destination_channel": null}'))
    if not CHANNEL_CONFIG["source_channels"] or not CHANNEL_CONFIG["destination_channel"]:
        logger.warning("Channel configuration is incomplete. Please configure source and destination channels.")
except json.JSONDecodeError:
    logger.error("Invalid channel configuration format. Please check the CHANNEL_CONFIG environment variable.")
    CHANNEL_CONFIG = {"source_channels": [], "destination_channel": None}

# Tag replacement configuration
try:
    # Format: {"@old_tag": "@new_tag", "t.me/old_channel": "t.me/new_channel", ...}
    TAG_CONFIG = json.loads(os.getenv("TAG_CONFIG", '{}'))
except json.JSONDecodeError:
    logger.error("Invalid tag configuration format. Please check the TAG_CONFIG environment variable.")
    TAG_CONFIG = {}

# Admin users who can control the bot (Telegram user IDs)
try:
    ADMIN_USERS = json.loads(os.getenv("ADMIN_USERS", "[7325746010]"))
except json.JSONDecodeError:
    logger.error("Invalid admin users format. Please check the ADMIN_USERS environment variable.")
    ADMIN_USERS = [7325746010]

# Additional configuration settings
try:
    # Format: {"CLEAN_MODE": "true", "sync_deletions": true, "OTHER_SETTING": "value"}
    BOT_CONFIG = json.loads(os.getenv("BOT_CONFIG", '{"CLEAN_MODE": "false", "sync_deletions": false}'))
except json.JSONDecodeError:
    logger.error("Invalid bot configuration format. Please check the BOT_CONFIG environment variable.")
    BOT_CONFIG = {"CLEAN_MODE": "false", "sync_deletions": False}

# Function to save bot configuration
def save_bot_config():
    """Save bot configuration to environment variable and .env file"""
    config_json = json.dumps(BOT_CONFIG)
    os.environ["BOT_CONFIG"] = config_json
    
    # Update .env file
    try:
        with open(".env", "r") as f:
            env_lines = f.readlines()
        
        # Check if BOT_CONFIG line exists
        bot_config_line_exists = False
        for i, line in enumerate(env_lines):
            if line.startswith("BOT_CONFIG="):
                env_lines[i] = f'BOT_CONFIG=\'{config_json}\'\n'
                bot_config_line_exists = True
                break
        
        # Add BOT_CONFIG if it doesn't exist
        if not bot_config_line_exists:
            env_lines.append(f'BOT_CONFIG=\'{config_json}\'\n')
        
        # Write back to .env
        with open(".env", "w") as f:
            f.writelines(env_lines)
            
        logger.info(f"Updated bot configuration in .env file: {config_json}")
    except Exception as e:
        logger.error(f"Failed to update .env file with bot configuration: {str(e)}")
        logger.info(f"Updated bot configuration in memory only: {config_json}")

# Remove Flask references
