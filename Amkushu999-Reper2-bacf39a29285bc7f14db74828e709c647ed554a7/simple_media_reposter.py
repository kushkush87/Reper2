#!/usr/bin/env python3
"""
Simple Telegram Media Reposter

This standalone script focuses solely on reposting media from source channels to destination channels
with minimal code and dependencies. It strips away all the complex bot menu functionality and just
handles the core reposting features.
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
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Telegram client imports
try:
    from telethon import TelegramClient, events
    from telethon.sessions import StringSession
    from telethon.tl.types import (
        MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
        InputChannel, PeerChannel, Channel, Chat, User
    )
except ImportError:
    logger.error("Telethon is required. Install with: pip install telethon")
    sys.exit(1)

# Environmental variables
API_ID = os.environ.get("API_ID")
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
USER_SESSION = os.environ.get("USER_SESSION")

# Channel configuration
try:
    source_channels_str = os.environ.get("SOURCE_CHANNELS", "[]")
    destination_channels_str = os.environ.get("DESTINATION_CHANNELS", "[]")
    
    import json
    source_channels = json.loads(source_channels_str.replace("'", '"')) if source_channels_str else []
    destination_channels = json.loads(destination_channels_str.replace("'", '"')) if destination_channels_str else []
    
    # Fallback to legacy format
    if not source_channels:
        source_channels = [int(os.environ.get("SOURCE_CHANNEL", 0))]
    if not destination_channels:
        destination_channels = [int(os.environ.get("DESTINATION_CHANNEL", 0))]
    
    logger.info(f"Source channels: {source_channels}")
    logger.info(f"Destination channels: {destination_channels}")
except Exception as e:
    logger.error(f"Error parsing channel configuration: {e}")
    source_channels = []
    destination_channels = []

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
        
        # Check media type and set appropriate extension
        if isinstance(message.media, MessageMediaPhoto):
            extension = ".jpg"
            media_type = "photo"
            logger.info("Media identified as PHOTO")
        elif isinstance(message.media, MessageMediaDocument):
            # Get MIME type if available
            document = message.media.document
            mime_type = document.mime_type if hasattr(document, 'mime_type') else None
            
            # Set extension based on MIME type
            if mime_type:
                if mime_type == "image/jpeg" or mime_type == "image/jpg":
                    extension = ".jpg"
                    media_type = "photo"
                elif mime_type == "image/png":
                    extension = ".png"
                    media_type = "photo"
                elif mime_type == "image/gif":
                    extension = ".gif"
                    media_type = "animation"
                elif mime_type == "video/mp4":
                    extension = ".mp4"
                    media_type = "video"
                elif mime_type == "audio/mpeg":
                    extension = ".mp3"
                    media_type = "audio"
                elif mime_type == "audio/ogg":
                    extension = ".ogg"
                    media_type = "voice"
                elif mime_type == "application/x-tgsticker":
                    extension = ".tgs"
                    media_type = "sticker"
                else:
                    media_type = "document"
            else:
                media_type = "document"
            
            logger.info(f"Media identified as {media_type} with extension {extension}")
        else:
            logger.warning(f"Unknown media type: {type(message.media).__name__}")
            return False
        
        # Define the download path
        file_path = os.path.join(temp_dir, f"media_{message.id}{extension}")
        logger.info(f"Downloading media to: {file_path}")
        
        # Download the media with optimized settings
        download_options = {
            'file': file_path,
            'progress_callback': None,
            'dc_id': None,
            'part_size_kb': 1024,  # 1MB chunks
            'workers': 4           # Multi-threaded download
        }
        
        # Perform the download
        downloaded_path = await message.download_media(**download_options)
        
        if not downloaded_path or not os.path.exists(downloaded_path):
            logger.error("Failed to download media: file doesn't exist")
            return False
        
        file_size = os.path.getsize(downloaded_path) if os.path.exists(downloaded_path) else 0
        logger.info(f"Successfully downloaded media ({file_size} bytes)")
        
        # Now repost to all destination channels
        caption = message.message if message.message else None
        
        for dest_channel in destination_channels:
            try:
                logger.info(f"Reposting media to channel: {dest_channel}")
                
                # Set up upload parameters
                upload_options = {
                    'caption': caption,
                    'parse_mode': 'html',
                    'force_document': False,
                    'part_size_kb': 1024,  # 1MB chunks for upload
                    'workers': 4           # Multi-threaded upload
                }
                
                # Add specific parameters based on media type
                if media_type == "video":
                    upload_options['video'] = True
                    upload_options['supports_streaming'] = True
                
                # Send the file
                sent_message = await user_client.send_file(
                    dest_channel,
                    downloaded_path,
                    **upload_options
                )
                
                logger.info(f"Successfully sent media to channel {dest_channel}")
            except Exception as send_error:
                logger.error(f"Error sending to channel {dest_channel}: {send_error}")
        
        # Clean up temporary files
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
        except Exception as cleanup_error:
            logger.warning(f"Failed to clean up temp directory: {cleanup_error}")
            
        return True
    except Exception as e:
        logger.error(f"Error processing media: {e}")
        return False

# Event handler for new messages
async def handle_new_message(event):
    """Handle new messages in source channels"""
    try:
        # Extract channel and message info
        channel_id = event.chat_id
        message_id = event.message.id
        logger.info(f"New message received: ID {message_id} in channel {channel_id}")
        
        # Get the full message
        message = event.message
        
        # Check if it has text
        if message.message:
            # Handle text message reposting
            text = message.message
            logger.info(f"Message text: {text[:50]}..." if len(text) > 50 else f"Message text: {text}")
            
            # Repost text to destination channels
            for dest_channel in destination_channels:
                try:
                    await user_client.send_message(
                        dest_channel,
                        text,
                        parse_mode='html'
                    )
                    logger.info(f"Reposted text message to channel {dest_channel}")
                except Exception as text_error:
                    logger.error(f"Error sending text to channel {dest_channel}: {text_error}")
        
        # Check if it has media
        if hasattr(message, 'media') and message.media:
            await download_and_repost_media(message)
    except Exception as e:
        logger.error(f"Error handling new message: {e}")

# Main function
async def main():
    """Main function to run the media reposter"""
    global user_client
    
    # Verify configuration
    if not API_ID or not API_HASH or not USER_SESSION:
        logger.error("API_ID, API_HASH, and USER_SESSION are required in .env file")
        return 1
    
    if not source_channels or not destination_channels:
        logger.error("Source and destination channels must be configured in .env file")
        return 1
    
    try:
        # Initialize the Telegram client
        logger.info(f"Initializing Telegram client with API_ID: {API_ID}")
        user_client = TelegramClient(
            StringSession(USER_SESSION),
            int(API_ID),
            API_HASH,
            connection_retries=None,  # Infinite retries
            retry_delay=1             # 1 second between retries
        )
        
        # Connect to Telegram
        await user_client.connect()
        
        # Check authorization
        if not await user_client.is_user_authorized():
            logger.error("User client is not authorized. Please generate a new session string.")
            return 1
        
        logger.info("User client connected and authorized successfully")
        
        # Add event handlers for source channels
        for source_channel in source_channels:
            user_client.add_event_handler(
                handle_new_message,
                events.NewMessage(chats=source_channel)
            )
            logger.info(f"Added event handler for source channel: {source_channel}")
        
        # Keep the script running
        logger.info("Simple Media Reposter is now running. Press Ctrl+C to stop.")
        
        # Create a basic ping to keep the connection alive
        while True:
            await asyncio.sleep(60)  # Sleep for 1 minute
            
    except KeyboardInterrupt:
        logger.info("Stopping by user request")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        return 1
    finally:
        # Disconnect the client
        if user_client:
            await user_client.disconnect()
            logger.info("Disconnected from Telegram")
    
    return 0

# Entry point
if __name__ == "__main__":
    # Set up event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(main())
    finally:
        loop.close()
    
    sys.exit(exit_code)
