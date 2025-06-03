#!/usr/bin/env python3
import os
import logging
import asyncio
import tempfile
from typing import Dict, Any, Optional
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage

# Configure logger for media handling
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Media handler functions
async def download_media(message) -> Dict[str, Any]:
    """Download media from a Telegram message and return metadata
    
    Args:
        message: The Telegram message containing media
        
    Returns:
        Dict with media info, including the file path and metadata
    """
    # Initialize the media data structure
    media_data = {
        "has_media": False,
        "media_info": None,
        "file_path": None,
        "caption": message.message if message.message else None
    }
    
    # Check if message has media
    if not hasattr(message, 'media') or not message.media:
        logger.info("Message has no media")
        return media_data
        
    logger.info(f"Processing media from message {message.id}")
    
    # Skip webpage previews
    if isinstance(message.media, MessageMediaWebPage):
        logger.info("Skipping webpage preview (not real media)")
        return media_data
    
    # Mark as having media
    media_data["has_media"] = True
    
    # Extract media type
    media_type = "unknown"
    is_photo = False
    is_video = False
    is_gif = False
    is_sticker = False
    is_voice = False
    is_audio = False
    is_document = False
    file_name = None
    mime_type = None
    
    try:
        # Handle photos
        if isinstance(message.media, MessageMediaPhoto):
            media_type = "photo"
            is_photo = True
            logger.info("Media identified as PHOTO")
        
        # Handle documents and other media types
        elif isinstance(message.media, MessageMediaDocument):
            document = message.media.document
            mime_type = document.mime_type if hasattr(document, 'mime_type') else None
            
            # Try to get filename from attributes
            for attr in document.attributes:
                if hasattr(attr, 'file_name') and attr.file_name:
                    file_name = attr.file_name
                    logger.info(f"Original filename: {file_name}")
                    break
            
            # Check various attribute types to determine media type
            for attr in document.attributes:
                # Video message
                if hasattr(attr, 'round_message') and attr.round_message:
                    media_type = "round"
                    is_video = True
                    logger.info("Media identified as ROUND VIDEO")
                    break
                    
                # Video or GIF
                elif hasattr(attr, 'video') and attr.video:
                    # Check if it's a GIF-like short video
                    if mime_type == "video/mp4" and hasattr(attr, 'duration') and attr.duration <= 15:
                        if any(hasattr(a, 'animated') and a.animated for a in document.attributes):
                            media_type = "gif"
                            is_gif = True
                            logger.info("Media identified as GIF")
                        else:
                            media_type = "video"
                            is_video = True
                            logger.info("Media identified as SHORT VIDEO")
                    else:
                        media_type = "video"
                        is_video = True
                        logger.info("Media identified as VIDEO")
                    break
                    
                # Voice message
                elif hasattr(attr, 'voice') and attr.voice:
                    media_type = "voice"
                    is_voice = True
                    logger.info("Media identified as VOICE MESSAGE")
                    break
                    
                # Audio file
                elif hasattr(attr, 'audio') and attr.audio:
                    media_type = "audio"
                    is_audio = True
                    logger.info("Media identified as AUDIO")
                    break
                    
                # Sticker
                elif hasattr(attr, 'sticker') and attr.sticker:
                    media_type = "sticker"
                    is_sticker = True
                    logger.info("Media identified as STICKER")
                    break
            
            # If no specific type identified, it's a document
            if media_type == "unknown":
                media_type = "document"
                is_document = True
                logger.info("Media identified as DOCUMENT (fallback)")
        
        # Determine file extension
        extension = ".bin"  # Default extension
        
        if mime_type:
            # Map common MIME types to extensions
            mime_to_ext = {
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "video/mp4": ".mp4",
                "audio/mpeg": ".mp3",
                "audio/ogg": ".ogg",
                "application/x-tgsticker": ".tgs"
            }
            extension = mime_to_ext.get(mime_type, ".bin")
            logger.info(f"Using extension {extension} based on MIME type")
        
        # Try to get extension from filename
        if file_name and '.' in file_name:
            extension = f'.{file_name.split(".")[-1]}'
            logger.info(f"Using extension {extension} from original filename")
        
        # Create a unique temp directory
        temp_dir = tempfile.mkdtemp(prefix="tg_media_")
        file_path = os.path.join(temp_dir, f"media_{message.id}{extension}")
        logger.info(f"Downloading media to {file_path}")
        
        # Download media with optimized settings
        download_options = {
            'file': file_path,
            'progress_callback': None,  # No progress callback to reduce overhead
            'dc_id': None,              # Let Telegram determine the DC
            'part_size_kb': 1024,       # Use 1MB chunks (1024 KB) instead of default 64KB
            'seekable_callback': None,  # No callback for seekability check
            'headers': None,            # No custom headers
            'workers': 4                # Use multiple workers for parallel download
        }
        
        # Start the download
        downloaded_path = await message.download_media(**download_options)
        
        # Verify the downloaded file exists
        if downloaded_path and os.path.exists(downloaded_path):
            file_size = os.path.getsize(downloaded_path)
            logger.info(f"Successfully downloaded media ({file_size} bytes) to {downloaded_path}")
            
            # Create media metadata
            media_data["media_info"] = {
                "type": media_type,
                "mime_type": mime_type,
                "file_name": file_name,
                "is_photo": is_photo,
                "is_video": is_video,
                "is_gif": is_gif,
                "is_sticker": is_sticker,
                "is_voice": is_voice,
                "is_audio": is_audio,
                "is_document": is_document
            }
            
            media_data["file_path"] = downloaded_path
            
            # For video, store additional attributes
            if is_video or is_gif:
                for attr in document.attributes:
                    if hasattr(attr, 'duration'):
                        media_data["media_info"]["duration"] = attr.duration
                    if hasattr(attr, 'w') and hasattr(attr, 'h'):
                        media_data["media_info"]["width"] = attr.w
                        media_data["media_info"]["height"] = attr.h
        else:
            logger.error("Failed to download media: file doesn't exist")
            media_data["has_media"] = False
    
    except Exception as e:
        logger.error(f"Error processing media: {str(e)}")
        media_data["has_media"] = False
    
    return media_data

async def send_media(client, channel_id, media_data):
    """Send media to a channel
    
    Args:
        client: The Telegram client
        channel_id: The destination channel ID
        media_data: The media data from download_media()
        
    Returns:
        The sent message or None if failed
    """
    if not media_data["has_media"] or not media_data["file_path"] or not os.path.exists(media_data["file_path"]):
        logger.error("Invalid media data or missing file")
        return None
    
    try:
        logger.info(f"Sending media to channel {channel_id}")
        
        # Common upload parameters
        upload_options = {
            'caption': media_data["caption"],
            'parse_mode': 'html',
            'force_document': False,
            'part_size_kb': 1024,  # Use 1MB chunks for upload
            'workers': 4           # Use multiple workers for faster upload
        }
        
        # Handle different media types
        media_info = media_data["media_info"]
        
        if media_info["is_video"] or media_info["is_gif"]:
            upload_options['video'] = True
            upload_options['supports_streaming'] = True
        
        # Send the file
        logger.info(f"Sending {media_info['type']} file: {media_data['file_path']}")
        sent_message = await client.send_file(
            channel_id,
            media_data["file_path"],
            **upload_options
        )
        
        logger.info(f"Successfully sent media to {channel_id}")
        return sent_message
    
    except Exception as e:
        logger.error(f"Error sending media: {str(e)}")
        return None
    
# Main function for testing
async def main():
    # This function can be used to test the module independently
    print("Media handler module loaded successfully")

if __name__ == "__main__":
    asyncio.run(main())
