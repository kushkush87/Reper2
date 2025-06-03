#!/usr/bin/env python3
"""
Fixed Telegram Media Reposter

This standalone script focuses solely on reposting media from source channels to destination channels
with minimal code and dependencies. It strips away all the complex bot menu functionality and just
handles the core reposting features.

This fixed version removes problematic parameters causing errors in media download.
"""

import os
import sys
import time
import logging
import asyncio
import tempfile
import shutil
from io import BytesIO
from typing import Dict, List, Any, Optional, Union
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    InputChannel, PeerChannel, Channel, Chat, User
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Environmental variables - set directly from known values
API_ID = 20584497
API_HASH = "9b77eafd4d379488e8de13b0324d6ef2"

# Get USER_SESSION from the environment or .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
    USER_SESSION = os.environ.get("USER_SESSION")
    if not USER_SESSION:
        # Try to read from main .env file
        if os.path.exists(".env"):
            with open(".env", "r") as f:
                for line in f.readlines():
                    if line.startswith("USER_SESSION="):
                        USER_SESSION = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
finally:
    if not USER_SESSION:
        logger.error("No USER_SESSION found! Cannot proceed without it.")
        USER_SESSION = None  # Will exit in main()

# Channel configuration
try:
    # Source and destination channel IDs
    SOURCE_CHANNELS = [2580593874]
    DESTINATION_CHANNELS = [2510014428]
    
    logger.info(f"Source channels: {SOURCE_CHANNELS}")
    logger.info(f"Destination channels: {DESTINATION_CHANNELS}")
except Exception as e:
    logger.error(f"Error setting up channel configuration: {e}")
    sys.exit(1)

# Global client variable
user_client = None

# Media handling functions
async def download_and_repost_media(message):
    """Download and repost media from a message"""
    logger.info(f"Processing media message ID: {message.id} from chat: {message.chat_id}")
    
    # Check if it's actually media
    if not hasattr(message, 'media') or not message.media:
        logger.info("Message has no media")
        return False
        
    # Skip webpage previews 
    if isinstance(message.media, MessageMediaWebPage):
        logger.info("Skipping webpage preview (not real media)")
        return False
    
    try:
        # Create a unique temporary directory for this media
        temp_dir = tempfile.mkdtemp(prefix="tg_media_")
        
        # Determine file extension based on media type
        extension = ".bin"  # Default
        media_type = "document"  # Default type
        
        # Check media type and set appropriate extension
        if isinstance(message.media, MessageMediaPhoto):
            extension = ".jpg"
            media_type = "photo"
            logger.info("Media identified as PHOTO")
        elif isinstance(message.media, MessageMediaDocument):
            # Try to get mime type
            if hasattr(message.media.document, 'mime_type'):
                mime_type = message.media.document.mime_type
                
                # Set extension based on MIME type
                if mime_type:
                    if mime_type.startswith("image/"):
                        extension = f".{mime_type.split('/')[1]}"
                        media_type = "photo"
                    elif mime_type.startswith("video/"):
                        extension = f".{mime_type.split('/')[1]}"
                        media_type = "video"
                    elif mime_type.startswith("audio/"):
                        extension = f".{mime_type.split('/')[1]}"
                        media_type = "audio"
            
            logger.info(f"Media identified as {media_type} with extension {extension}")
        else:
            logger.warning(f"Unknown media type: {type(message.media).__name__}")
            return False
        
        # Define the download path
        file_path = os.path.join(temp_dir, f"media_{message.id}{extension}")
        logger.info(f"Downloading media to: {file_path}")
        
        # Download the media with simplified parameters
        downloaded_file = await message.download_media(file=file_path)
        
        if not downloaded_file or not os.path.exists(downloaded_file):
            logger.error("Failed to download media file")
            return False
            
        logger.info(f"Successfully downloaded media to {downloaded_file}")
        
        # Get caption if any
        caption = message.message if hasattr(message, 'message') else None
        logger.info(f"Caption: {caption[:50] + '...' if caption and len(caption) > 50 else caption}")
        
        # Send media to all destination channels
        success_count = 0
        for dest_channel in DESTINATION_CHANNELS:
            try:
                logger.info(f"Sending media to destination channel: {dest_channel}")
                
                # Determine how to send based on media type
                if media_type == "photo":
                    sent_message = await user_client.send_file(
                        dest_channel,
                        file=downloaded_file,
                        caption=caption
                    )
                elif media_type == "video":
                    sent_message = await user_client.send_file(
                        dest_channel,
                        file=downloaded_file,
                        caption=caption,
                        supports_streaming=True
                    )
                elif media_type in ["audio", "voice"]:
                    sent_message = await user_client.send_file(
                        dest_channel,
                        file=downloaded_file,
                        caption=caption,
                        voice_note=(media_type == "voice")
                    )
                else:  # document or unknown
                    sent_message = await user_client.send_file(
                        dest_channel,
                        file=downloaded_file,
                        caption=caption
                    )
                    
                if sent_message:
                    logger.info(f"Successfully sent media to {dest_channel}")
                    success_count += 1
                
            except Exception as e:
                logger.error(f"Error sending media to channel {dest_channel}: {str(e)}")
        
        # Clean up the temporary directory
        try:
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp dir {temp_dir}: {str(e)}")
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error processing media: {str(e)}")
        # Clean up if possible
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except:
            pass
        return False

async def handle_new_message(event):
    """Handle new messages in source channels"""
    try:
        # Get message from event
        message = event.message
        
        # Get source channel
        source_channel = event.chat_id
        
        logger.info(f"New message from channel {source_channel}: {message.id}")
        
        # Check if this is media
        if hasattr(message, 'media') and message.media:
            success = await download_and_repost_media(message)
            if success:
                logger.info(f"Successfully reposted media from message {message.id}")
            else:
                logger.warning(f"Failed to repost media from message {message.id}")
        else:
            # It's text only, forward the text content
            if hasattr(message, 'message') and message.message:
                text = message.message
                for dest_channel in DESTINATION_CHANNELS:
                    try:
                        sent = await user_client.send_message(dest_channel, text)
                        if sent:
                            logger.info(f"Forwarded text message to channel {dest_channel}")
                    except Exception as e:
                        logger.error(f"Error forwarding text to channel {dest_channel}: {str(e)}")
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")

async def main():
    """Main function to start the media reposter"""
    global user_client
    
    # Verify we have required credentials
    if not API_ID or not API_HASH or not USER_SESSION:
        logger.error("Missing required credentials. Please set API_ID, API_HASH, and USER_SESSION")
        return 1
        
    # Make sure API_ID is an integer
    api_id_int = int(API_ID) if isinstance(API_ID, str) else API_ID
    
    # Initial Telethon client setup
    logger.info(f"Initializing Telegram client with API_ID: {api_id_int}")
    user_client = TelegramClient(StringSession(USER_SESSION), api_id_int, API_HASH)
    
    try:
        # Connect and sign in
        await user_client.start()
        
        # Check authentication
        if await user_client.is_user_authorized():
            logger.info("User client connected and authorized successfully")
        else:
            logger.error("User client failed to authenticate. Check your session string.")
            return 1
        
        # Register event handlers for each source channel
        for source_channel in SOURCE_CHANNELS:
            user_client.add_event_handler(
                handle_new_message,
                events.NewMessage(chats=source_channel)
            )
            logger.info(f"Added event handler for source channel: {source_channel}")
        
        logger.info("Simple Media Reposter is now running. Press Ctrl+C to stop.")
        
        # Keep the script running
        while True:
            await asyncio.sleep(60)  # Sleep for a minute to prevent CPU usage
            
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logger.error(f"Error in main function: {str(e)}")
        return 1
    finally:
        # Disconnect the client when done
        await user_client.disconnect()
        logger.info("User client disconnected")
    
    return 0

if __name__ == "__main__":
    # Create and run the event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(main())
    finally:
        loop.close()
        
    sys.exit(exit_code)
