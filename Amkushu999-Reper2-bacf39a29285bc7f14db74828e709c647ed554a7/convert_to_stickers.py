#!/usr/bin/env python3
"""
Helper script to create stickers from videos and images in attached_assets directory

This script will help convert your videos and images to stickers by sending them to @Stickers or @Fstikbot
"""

import os
import sys
import asyncio
import logging
import argparse
from telethon import TelegramClient
from telethon.sessions import StringSession

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Get API config from environment or config files
try:
    import config
    API_ID = config.API_ID
    API_HASH = config.API_HASH
    USER_SESSION = config.USER_SESSION
except (ImportError, AttributeError):
    API_ID = os.environ.get('API_ID')
    API_HASH = os.environ.get('API_HASH')
    USER_SESSION = os.environ.get('USER_SESSION')

if not API_ID or not API_HASH or not USER_SESSION:
    logger.error("Please set API_ID, API_HASH and USER_SESSION as environment variables or in config.py")
    sys.exit(1)

async def get_rawdatabot_info():
    """Get sticker ID information from RawDataBot"""
    client = TelegramClient(StringSession(USER_SESSION), API_ID, API_HASH)
    await client.start()
    
    try:
        rawdatabot = await client.get_entity("@RawDataBot")
        
        # Send instructions to the user
        print("\n")
        print("=======================================================")
        print("INSTRUCTIONS TO GET STICKER IDs:")
        print("=======================================================")
        print("1. Find your newly created stickers in your sticker collection")
        print("2. Forward each sticker to @RawDataBot")
        print("3. Look for the 'sticker_id' value in the response")
        print("4. Add these sticker IDs to assets/stickers/constants.py")
        print("=======================================================")
        
        # Just print instructions instead of automating
        print("To update your farewell stickers list, add your new sticker IDs to the FAREWELL_STICKERS list")
        print("in the assets/stickers/constants.py file.")
        
    except Exception as e:
        logger.error(f"Error with RawDataBot instructions: {str(e)}")
    finally:
        await client.disconnect()

async def send_to_stickers_bot(image_paths):
    """Send images to official @Stickers bot"""
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
                
            if path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                # Send as photo for sticker creation
                logger.info(f"Sending {path} to @Stickers bot")
                await client.send_file(stickers_bot, path)
            elif path.lower().endswith(('.mp4', '.webm', '.gif')):
                # For video/animated stickers
                logger.info(f"Sending {path} to @Stickers bot (video/animation)")
                await client.send_file(stickers_bot, path)
        
        logger.info("Done sending files to @Stickers bot")
        logger.info("Now follow the bot's instructions to create your stickers")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        await client.disconnect()

async def send_to_fstik_bot(image_paths):
    """Send images to @Fstikbot for easier sticker creation"""
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
        logger.info("Now follow the bot's instructions to create your stickers")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        await client.disconnect()

async def add_stickers_to_constants(sticker_ids):
    """Add sticker IDs to the constants file"""
    constants_file = "assets/stickers/constants.py"
    
    if not os.path.exists(constants_file):
        logger.error(f"Constants file not found: {constants_file}")
        return
    
    # Read current constants file
    with open(constants_file, 'r') as f:
        lines = f.readlines()
    
    # Find the FAREWELL_STICKERS list
    start_idx = -1
    end_idx = -1
    for i, line in enumerate(lines):
        if "FAREWELL_STICKERS = [" in line:
            start_idx = i
        if start_idx != -1 and "]" in line and end_idx == -1:
            end_idx = i
    
    if start_idx == -1 or end_idx == -1:
        logger.error("Couldn't find FAREWELL_STICKERS list in constants file")
        return
    
    # Add new sticker IDs before the closing bracket
    new_lines = lines[:end_idx]
    for sticker_id in sticker_ids:
        new_lines.append(f"    \"{sticker_id}\",  # Added sticker\n")
    new_lines.extend(lines[end_idx:])
    
    # Write updated file
    with open(constants_file, 'w') as f:
        f.writelines(new_lines)
    
    logger.info(f"Added {len(sticker_ids)} sticker IDs to {constants_file}")

def get_media_files(directory):
    """Get all media files in the specified directory"""
    if not os.path.exists(directory):
        logger.error(f"Directory not found: {directory}")
        return []
    
    # File extensions we can use
    image_extensions = ('.jpg', '.jpeg', '.png', '.webp')
    video_extensions = ('.mp4', '.webm', '.gif', '.tgs')
    allowed_extensions = image_extensions + video_extensions
    
    # Find all valid files
    media_files = []
    for file in os.listdir(directory):
        if file.lower().endswith(allowed_extensions) and not file.startswith('.'):
            media_files.append(os.path.join(directory, file))
    
    return media_files

async def main():
    parser = argparse.ArgumentParser(description="Convert images and videos to Telegram stickers")
    parser.add_argument(
        '--dir', '-d', 
        default='attached_assets',
        help='Directory containing media files to convert (default: attached_assets)'
    )
    parser.add_argument(
        '--bot', '-b',
        choices=['stickers', 'fstik'],
        default='fstik',
        help='Which bot to use for sticker creation (default: fstik)'
    )
    parser.add_argument(
        '--help-only',
        action='store_true',
        help='Just print instructions without sending files'
    )
    
    args = parser.parse_args()
    
    # If help only, just print instructions and exit
    if args.help_only:
        print("\n")
        print("=======================================================")
        print("INSTRUCTIONS FOR CREATING TELEGRAM STICKERS:")
        print("=======================================================")
        print("This script helps you convert images and videos to Telegram stickers.")
        print("\nTo create stickers:")
        print("1. Place your images/videos in the 'attached_assets' directory")
        print("2. Run this script to send them to a sticker creation bot")
        print("3. Follow the bot's instructions to create your sticker pack")
        print("4. Forward each created sticker to @RawDataBot to get its ID")
        print("5. Add the sticker IDs to assets/stickers/constants.py")
        print("\nExample usage:")
        print("python convert_to_stickers.py --bot fstik      # Use @Fstikbot (easier)")
        print("python convert_to_stickers.py --bot stickers  # Use @Stickers (official)")
        print("=======================================================")
        await get_rawdatabot_info()
        return
    
    # Get media files
    media_files = get_media_files(args.dir)
    
    if not media_files:
        logger.error(f"No media files found in {args.dir}")
        return
    
    print(f"Found {len(media_files)} media files to convert to stickers:")
    for i, path in enumerate(media_files, 1):
        print(f"{i}. {os.path.basename(path)}")
    
    # Confirm with user
    confirmation = input(f"\nSend these {len(media_files)} files to @{args.bot.capitalize()}bot? (y/n): ")
    if confirmation.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Send to appropriate bot
    if args.bot == 'stickers':
        await send_to_stickers_bot(media_files)
    else:  # fstik
        await send_to_fstik_bot(media_files)
    
    # Provide instructions for getting sticker IDs
    await get_rawdatabot_info()

if __name__ == "__main__":
    asyncio.run(main())
