import os
import sys
import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get configuration from environment
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
USER_SESSION = os.environ.get('USER_SESSION')
BOT_TOKEN = os.environ.get('BOT_TOKEN')

async def send_stickers_to_bot(image_paths):
    """Send images to @Stickers bot to create stickers"""
    if not API_ID or not API_HASH or not USER_SESSION:
        logger.error("API_ID, API_HASH and USER_SESSION environment variables are required")
        return False
        
    # Initialize client
    client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
    await client.start()
    
    try:
        # Get @Stickers bot entity
        stickers_bot = await client.get_entity("@Stickers")
        
        # Now upload each image to the stickers bot
        for path in image_paths:
            if not os.path.exists(path):
                logger.error(f"File not found: {path}")
                continue
                
            if path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp', '.tgs')):
                # Send as photo for sticker creation
                logger.info(f"Sending {path} to @Stickers bot")
                await client.send_file(stickers_bot, path)
            elif path.lower().endswith(('.mp4', '.webm')):
                # For video stickers
                logger.info(f"Sending {path} to @Stickers bot (video)")
                await client.send_file(stickers_bot, path, attributes=[{"animated": True}])
        
        logger.info("Done sending files to @Stickers bot")
        logger.info("Now you need to follow the bot's instructions to create the stickers")
        logger.info("Once created, get the sticker ID and add it to FAREWELL_STICKERS in assets/stickers/constants.py")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return False
    finally:
        await client.disconnect()
    
    return True

async def send_to_sticker_creation_bot(image_paths):
    """Send images to @Fstikbot for easier sticker creation"""
    if not API_ID or not API_HASH or not USER_SESSION:
        logger.error("API_ID, API_HASH and USER_SESSION environment variables are required")
        return False
        
    # Initialize client
    client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
    await client.start()
    
    try:
        # Get @Fstikbot entity
        fstikbot = await client.get_entity("@Fstikbot")
        
        # Now upload each image to the stickers bot
        for path in image_paths:
            if not os.path.exists(path):
                logger.error(f"File not found: {path}")
                continue
                
            # Send to bot
            logger.info(f"Sending {path} to @Fstikbot")
            await client.send_file(fstikbot, path)
        
        logger.info("Done sending files to @Fstikbot")
        logger.info("Now you need to follow the bot's instructions to create the stickers")
        logger.info("Once created, get the sticker ID and add it to FAREWELL_STICKERS in assets/stickers/constants.py")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return False
    finally:
        await client.disconnect()
    
    return True

def print_instructions():
    print("===========================================================")
    print("Instructions for creating Telegram stickers")
    print("===========================================================")
    print("\nThis script will help you convert your images/videos to Telegram stickers.")
    print("\nChoose one of the following options:")
    print("1. Send images/videos to @Stickers bot")
    print("2. Send images/videos to @Fstikbot (easier)")
    print("\nAfter creating the stickers, you'll need to get the sticker IDs and add them to the")
    print("FAREWELL_STICKERS list in assets/stickers/constants.py")
    print("\nTo get the sticker ID after creation:")
    print("1. Find the sticker in your sticker collection")
    print("2. Forward it to @RawDataBot")
    print("3. Look for 'sticker_id' in the response")
    print("4. Add that ID to the FAREWELL_STICKERS list")
    print("===========================================================")

async def main():
    # Get all image and video files in the attached_assets directory
    asset_dir = "attached_assets"
    
    # Check if directory exists
    if not os.path.exists(asset_dir):
        logger.error(f"Directory not found: {asset_dir}")
        return
        
    # Find all image and video files
    image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.tgs')
    video_extensions = ('.mp4', '.webm')
    allowed_extensions = image_extensions + video_extensions
    
    image_paths = []
    for file in os.listdir(asset_dir):
        if file.lower().endswith(allowed_extensions) and not file.startswith('.'):
            image_paths.append(os.path.join(asset_dir, file))
    
    if not image_paths:
        logger.error(f"No image or video files found in {asset_dir}")
        return
        
    print_instructions()
    print(f"\nFound {len(image_paths)} image/video files in {asset_dir}:")
    for i, path in enumerate(image_paths, 1):
        print(f"{i}. {os.path.basename(path)}")
        
    # Ask user which bot to use
    choice = input("\nWhich bot would you like to use? (1 for @Stickers, 2 for @Fstikbot): ")
    
    if choice == "1":
        await send_stickers_to_bot(image_paths)
    elif choice == "2":
        await send_to_sticker_creation_bot(image_paths)
    else:
        print("Invalid choice. Please enter 1 or 2.")

if __name__ == "__main__":
    asyncio.run(main())
