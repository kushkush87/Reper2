import os
import logging
import asyncio
import tempfile
import json
import re  # Regular expression module
import sys
import datetime
from io import BytesIO
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import timezone

# Module-level variable to track reposting state
reposting_active = True  # Default to active


from telethon import TelegramClient, events, functions
from telethon.sessions import StringSession
from telethon.tl.types import (
    Message, MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage,
    InputChannel, PeerChannel, Channel, Chat, User,
    MessageEntityTextUrl, MessageEntityUrl, MessageEntityMention,
    ChannelParticipantsAdmins
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest, GetParticipantsRequest
from telethon.errors import (
    ChannelPrivateError, ChannelInvalidError, 
    FloodWaitError, ChatAdminRequiredError,
    UserAdminInvalidError
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters, Defaults

from config import (
    BOT_TOKEN, API_ID, API_HASH, USER_SESSION, 
    CHANNEL_CONFIG, TAG_CONFIG, ADMIN_USERS, BOT_CONFIG,
    save_bot_config, logger
)

# Import sticker constants
try:
    from assets.stickers.constants import FAREWELL_STICKER_ID, FAREWELL_STICKERS
except ImportError:
    logger.warning("Sticker constants not found, using default values")
    FAREWELL_STICKER_ID = "CAACAgIAAxkBAAELR65j645BzPj-1pVthQmCrMK1j_JsxQACuRUAAubQyEs-8Sg8_BmPFi8E"  # Default
    FAREWELL_STICKERS = [FAREWELL_STICKER_ID]  # Default list

# Toggle for deletion synchronization
sync_deletions = BOT_CONFIG.get("sync_deletions", False)

# Default sticker ID to send before leaving a channel (CATuDio waving goodbye sticker)
farewell_sticker_id = BOT_CONFIG.get("farewell_sticker_id", "CAACAgIAAxkBAAELR65j645BzPj-1pVthQmCrMK1j_JsxQACuRUAAubQyEs-8Sg8_BmPFi8E")

# Channel management settings
channel_settings = {
    "farewell_sticker_id": farewell_sticker_id  # Default sticker ID
}

# Memory storage for active source channels and destination(s)
active_channels = {
    "source": CHANNEL_CONFIG.get("source_channels", []),
    "destination": CHANNEL_CONFIG.get("destination_channel"),
    "destinations": CHANNEL_CONFIG.get("destination_channels", [])
}

# If we have an old-style single destination but no destinations array, initialize it
if active_channels["destination"] and not active_channels["destinations"]:
    active_channels["destinations"] = [active_channels["destination"]]
    logger.info(f"Initialized destinations array with legacy destination: {active_channels['destination']}")

# Content filter configuration (keywords and media types to include/exclude)
content_filters = {
    "enabled": False,  # Force disable content filters to allow all media
    "keywords": {
        "include": BOT_CONFIG.get("filter_include_keywords", []),
        "exclude": BOT_CONFIG.get("filter_exclude_keywords", [])
    },
    "media_types": {
        "include": [],  # Empty include list means all media types are allowed
        "exclude": BOT_CONFIG.get("filter_exclude_media", [])
    }
}

# Channel management settings
channel_settings = {
    "farewell_sticker_id": FAREWELL_STICKER_ID
}

# Default farewell sticker ID (used when leaving a channel after purging)
farewell_sticker_id = FAREWELL_STICKER_ID

# Memory storage for tag replacements
tag_replacements = TAG_CONFIG.copy()

# Get current destination tag
destination_channel = CHANNEL_CONFIG.get("destination_channel")
destination_tag = None

# If we have a destination channel, create default tag replacements for t.me links
if destination_channel:
    try:
        # Get info about destination
        entity_info = None
        # If this is a number, it's likely a channel ID
        if isinstance(destination_channel, int) or (isinstance(destination_channel, str) and destination_channel.lstrip('-').isdigit()):
            # Numeric ID - set a default replacement
            destination_tag = f"@destination{abs(int(destination_channel))}"  # Just a placeholder
            logger.info(f"Using placeholder tag '{destination_tag}' for numeric channel ID")
            
            # Add default t.me replacements
            # This will ensure any t.me links are replaced even if not explicitly configured
            if destination_tag:
                logger.info(f"Adding default t.me replacements with destination tag {destination_tag}")
                # Add basic replacement patterns for t.me links
                # We'll add these to tag_replacements only if they don't exist yet
                if destination_tag.startswith("@"):
                    username = destination_tag[1:]  # Remove @ symbol
                    if not f"t.me/joinchat/" in tag_replacements:
                        tag_replacements[f"t.me/joinchat/"] = f"t.me/{username}"
                    if not f"t.me/+" in tag_replacements:
                        tag_replacements[f"t.me/+"] = f"t.me/{username}"
                    if not f"https://t.me/joinchat/" in tag_replacements:
                        tag_replacements[f"https://t.me/joinchat/"] = f"https://t.me/{username}"
                    if not f"https://t.me/+" in tag_replacements:
                        tag_replacements[f"https://t.me/+"] = f"https://t.me/{username}"
                        
                    logger.info(f"Added {len(tag_replacements)} default t.me replacement patterns")
    except Exception as e:
        logger.error(f"Error setting up default tag replacements: {str(e)}")
        logger.info("Will continue with explicitly configured tag replacements only")

# Dictionary to track message IDs per user and chat to clean up old messages
user_message_history = {}

# Define function to save reposting state
def save_reposting_state():
    """Save the current reposting state to the bot configuration"""
    global reposting_active
    # Update bot config
    BOT_CONFIG["reposting_active"] = reposting_active
    # Save to file/env
    save_bot_config()
    logger.info(f"Saved reposting state: {reposting_active}")

# Initialize reposting from config if available
if "reposting_active" in BOT_CONFIG:
    reposting_active = BOT_CONFIG["reposting_active"]
    logger.info(f"Loaded reposting state from config: {reposting_active}")
else:
    # Make sure our initial state is saved
    try:
        save_reposting_state()
    except Exception as e:
        logger.error(f"Failed to save initial reposting state: {e}")


# Content filtering function
async def filter_content(msg_data: Dict[str, Any]) -> bool:
    """Filter message based on content filters
    Returns True if message should be reposted, False if it should be filtered out"""
    # Skip filtering if filters are disabled
    if not content_filters["enabled"]:
        return True
        
    # Get filter settings
    include_keywords = content_filters["keywords"]["include"]
    exclude_keywords = content_filters["keywords"]["exclude"]
    include_media = content_filters["media_types"]["include"]
    exclude_media = content_filters["media_types"]["exclude"]
    
    # Media type filtering
    if msg_data["has_media"]:
        media_type = msg_data["media_data"]["type"]
        
        # If we have an include list and this type isn't in it, filter out
        if include_media and media_type not in include_media:
            logger.info(f"Filtering out message with media type {media_type} (not in include list)")
            return False
            
        # If this type is in the exclude list, filter out
        if exclude_media and media_type in exclude_media:
            logger.info(f"Filtering out message with media type {media_type} (in exclude list)")
            return False
    
    # Keyword filtering for text in messages
    content_text = ""
    
    # Get text content depending on message type
    if msg_data["has_media"] and msg_data["media_data"]["caption"]:
        content_text = msg_data["media_data"]["caption"]
    elif not msg_data["has_media"] and msg_data["text"]:
        content_text = msg_data["text"]
    
    # No text to filter if content_text is empty
    if not content_text:
        # If we have include keywords but no text, we can't match - so filter out
        if include_keywords:
            logger.info("Filtering out message with no text (include keywords specified)")
            return False
        # Otherwise, let it pass through the media filters
        return True
        
    # Convert content to lowercase for case-insensitive matching
    content_lower = content_text.lower()
    
    # Check include keywords - if any are specified, at least one must match
    if include_keywords:
        matched = False
        for keyword in include_keywords:
            if keyword.lower() in content_lower:
                matched = True
                break
        if not matched:
            logger.info("Filtering out message (no include keywords matched)")
            return False
    
    # Check exclude keywords - if any match, filter out
    if exclude_keywords:
        for keyword in exclude_keywords:
            if keyword.lower() in content_lower:
                logger.info(f"Filtering out message (matched exclude keyword: {keyword})")
                return False
    
    # If we got here, the message passed all filters
    return True

async def normalize_channel_id(channel_input: Union[int, str]) -> Union[int, str]:
    """
    Normalize channel input to a usable format for Telegram API
    Handles t.me links, @usernames, and numeric IDs
    
    Returns the normalized channel ID or username
    """
    original_input = channel_input
    
    try:
        # Handle string inputs
        if isinstance(channel_input, str):
            # Handle t.me links with improved pattern
            t_me_pattern = r'(?:https?://)?(?:t|telegram)\.me/(?:joinchat/)?([a-zA-Z0-9_\-]+)'
            t_me_match = re.search(t_me_pattern, channel_input)
            
            if t_me_match:
                # Extract username or invite code from t.me link
                channel_input = t_me_match.group(1)
                logger.info(f"Extracted username/code from t.me link: {channel_input}")
                
            # Handle @username format
            elif channel_input.startswith('@'):
                channel_input = channel_input[1:]  # Remove the @ symbol
                logger.info(f"Using username without @: {channel_input}")
                
            # Handle numeric string IDs
            elif channel_input.lstrip('-').isdigit():
                channel_input = int(channel_input)
                logger.info(f"Converted string ID to integer: {channel_input}")
                
            # Log the final format for debugging
            logger.info(f"Normalized channel ID: {channel_input} (type: {type(channel_input).__name__})")
    except Exception as e:
        logger.error(f"Error normalizing channel ID {original_input}: {e}")
        # Return original if we can't process it
        return original_input
        
    return channel_input
# Initialize the Telegram user client with the session if credentials are available
user_client = None
if API_ID and API_HASH and USER_SESSION:
    try:
        # Make sure API_ID is an integer
        api_id_int = int(API_ID) if isinstance(API_ID, str) else API_ID
        # Create the client with proper credentials
        user_client = TelegramClient(StringSession(USER_SESSION), api_id_int, API_HASH)
        logger.info(f"User client initialized with API_ID: {api_id_int}")
    except Exception as e:
        logger.error(f"Error initializing user client: {str(e)}")
        # Still keep the client as None in case of errors

# Helper functions

async def get_entity_info(client: TelegramClient, entity_id: Union[int, str]) -> Optional[Dict[str, Any]]:
    """Get information about a channel/chat/user entity"""
    try:
        # Keep the original for error reporting
        original_entity_id = entity_id  
        
        try:
            # Use our channel ID normalizer function
            entity_id = await normalize_channel_id(entity_id)
            
            # For negative IDs (supergroups/channels), ensure proper format
            if isinstance(entity_id, int) and entity_id < 0:
                # Convert to proper channel ID format if needed
                # Telegram channel IDs are typically large negative numbers
                # We need to convert to PeerChannel format for proper access
                try:
                    entity_id = PeerChannel(channel_id=int(str(entity_id).lstrip('-')))
                    logger.info(f"Converted negative ID to PeerChannel format")
                except Exception as e:
                    logger.warning(f"Failed to convert negative ID to PeerChannel: {e}")
            
            # For positive IDs, could be users or channels
            if isinstance(entity_id, int) and entity_id > 1000000000:
                # Large positive IDs are typically channels/chats
                try:
                    # Try as channel first
                    entity_id = PeerChannel(channel_id=entity_id)
                    logger.info(f"Converted large positive ID to PeerChannel format")
                except Exception as e:
                    # If that fails, leave as is
                    logger.warning(f"Failed to convert large ID to PeerChannel: {e}")
        except Exception as e:
            logger.warning(f"Error processing entity ID format: {str(e)}")
        
        # Check if client is connected
        if not client or not client.is_connected():
            try:
                if client:
                    logger.info("Client not connected. Attempting to connect...")
                    await client.connect()
                    if not client.is_connected():
                        logger.error("Failed to connect client")
                        raise ConnectionError("Cannot connect to Telegram servers")
                else:
                    logger.error("No client available")
                    raise ValueError("No Telegram client available. Please configure API credentials")
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                raise ConnectionError(f"Connection error: {str(e)}")
        
        # Get the entity with the potentially corrected format
        try:
            entity = await client.get_entity(entity_id)
        except Exception as e:
            logger.error(f"Error getting entity {entity_id}: {str(e)}")
            
            # Try a different approach for usernames
            if isinstance(original_entity_id, str):
                # If original was a username or link, try different formats
                if '@' in original_entity_id or '/' in original_entity_id:
                    clean_username = original_entity_id.replace('@', '').split('/')[-1]
                    logger.info(f"Retrying with cleaned username: {clean_username}")
                    try:
                        entity = await client.get_entity(clean_username)
                    except Exception as retry_error:
                        logger.error(f"Retry failed: {str(retry_error)}")
                        raise ValueError(f"Cannot find channel/user: {original_entity_id}. Please try using a numeric ID.")
                else:
                    raise
        
        if isinstance(entity, (Channel, Chat)):
            return {
                "id": entity.id,
                "title": entity.title,
                "username": getattr(entity, "username", None),
                "type": "channel" if getattr(entity, "broadcast", False) else "group",
                "accessible": True
            }
        elif isinstance(entity, User):
            return {
                "id": entity.id,
                "title": f"{entity.first_name} {entity.last_name if entity.last_name else ''}".strip(),
                "username": getattr(entity, "username", None),
                "type": "user",
                "accessible": True
            }
        return None
    except ChannelPrivateError:
        # Special handling for private channels
        logger.warning(f"Channel {entity_id} is private or user lacks permission to access it")
        return {
            "id": entity_id if isinstance(entity_id, int) else 0,
            "title": "Private Channel (No Access)",
            "username": None,
            "type": "channel",
            "accessible": False
        }
    except Exception as e:
        logger.error(f"Failed to get entity for {entity_id}: {str(e)}")
        
        # Return a placeholder for display purposes
        id_value = entity_id
        if isinstance(entity_id, PeerChannel):
            id_value = entity_id.channel_id
        elif not isinstance(id_value, int) and not isinstance(id_value, str):
            id_value = str(id_value)
            
        return {
            "id": id_value if isinstance(id_value, int) else 0,
            "title": f"Unknown ({id_value})",
            "username": None,
            "type": "unknown",
            "accessible": False,
            "error": str(e)
        }

async def join_channel(client: TelegramClient, channel_id: Union[int, str]) -> bool:
    """Attempt to join a channel using the user client"""
    original_channel_id = channel_id
    
    try:
        # Use our channel ID normalizer function
        channel_id = await normalize_channel_id(channel_id)
        
        # Get entity and join
        entity = await client.get_entity(channel_id)
        await client(JoinChannelRequest(entity))
        logger.info(f"Successfully joined channel: {getattr(entity, 'title', channel_id)}")
        return True
    except ChannelPrivateError:
        logger.error(f"Cannot join private channel: {original_channel_id}")
        return False
    except ChannelInvalidError:
        logger.error(f"Invalid channel: {original_channel_id}")
        return False
    except ValueError as e:
        logger.error(f"Channel value error: {str(e)}")
        # Try alternative formatting for the channel
        try:
            if isinstance(original_channel_id, str):
                # Clean up the username if it was in a special format
                clean_id = original_channel_id.replace('@', '')
                if '/' in clean_id:  # Handle URL format
                    clean_id = clean_id.split('/')[-1]
                
                logger.info(f"Retrying join with cleaned ID: {clean_id}")
                entity = await client.get_entity(clean_id)
                await client(JoinChannelRequest(entity))
                logger.info(f"Successfully joined channel on retry: {getattr(entity, 'title', clean_id)}")
                return True
        except Exception as retry_error:
            logger.error(f"Failed to join channel on retry: {str(retry_error)}")
        return False
    except Exception as e:
        logger.error(f"Failed to join channel {original_channel_id}: {str(e)}")
        return False

async def save_config():
    """Save current channel configuration to environment variable and .env file"""
    config = {
        "source_channels": active_channels["source"],
        "destination_channel": active_channels["destination"],
        "destination_channels": active_channels["destinations"]
    }
    config_json = json.dumps(config)
    os.environ["CHANNEL_CONFIG"] = config_json
    
    # Update the .env file to persist the configuration
    try:
        # Read the current .env file
        with open(".env", "r") as env_file:
            env_content = env_file.read()
        
        # Check if CHANNEL_CONFIG already exists in the file
        if "CHANNEL_CONFIG=" in env_content:
            # Replace existing value
            new_env_content = re.sub(
                r'CHANNEL_CONFIG=.*', 
                f'CHANNEL_CONFIG=\'{config_json}\'', 
                env_content
            )
        else:
            # Add new entry
            new_env_content = env_content + f'\nCHANNEL_CONFIG=\'{config_json}\''
        
        # Write back to .env file
        with open(".env", "w") as env_file:
            env_file.write(new_env_content)
            
        logger.info(f"Updated channel configuration in .env file and memory: {config_json}")
    except Exception as e:
        logger.error(f"Failed to update .env file with channel configuration: {str(e)}")
        logger.info(f"Updated channel configuration in memory only: {config_json}")
    
    # Update event handlers for new source channels if user client is connected
    # Important: Only proceed if the client is available and connected
    if user_client and user_client.is_connected():
        logger.info(f"Updating event handlers for source channels: {active_channels['source']}")
        
        # Auto-join new source channels
        if active_channels["source"]:
            logger.info("Checking if we need to join any source channels...")
            for channel in active_channels["source"]:
                try:
                    # Try to get entity info to check if we're already in the channel
                    entity_info = await get_entity_info(user_client, channel)
                    
                    # If we can't get entity info, we might need to join
                    if not entity_info:
                        logger.info(f"Attempting to join source channel: {channel}")
                        join_success = await join_channel(user_client, channel)
                        if join_success:
                            logger.info(f"Successfully joined source channel: {channel}")
                        else:
                            logger.warning(f"Failed to join source channel: {channel}")
                    else:
                        logger.info(f"Already have access to source channel: {channel}")
                except Exception as e:
                    logger.error(f"Error checking/joining channel {channel}: {str(e)}")
        
        # First remove all existing handlers for this event type
        # Create a copy of the event builders list since we'll modify it
        if hasattr(user_client, '_event_builders'):
            builders = list(user_client._event_builders)
            for builder in builders:
                if isinstance(builder[0], events.NewMessage):
                    user_client.remove_event_handler(builder[1], builder[0])
        
        # Now add the updated handlers
        if active_channels["source"]:
            logger.info(f"Registering event handler for source channels: {active_channels['source']}")
            # Extra logging to diagnose event handlers
            logger.info(f"Current event handlers: {len(user_client._event_builders) if hasattr(user_client, '_event_builders') else 0}")
            
            user_client.add_event_handler(
                handle_new_message,
                events.NewMessage(chats=active_channels["source"])
            )
            
            # Add handler for edited messages
            user_client.add_event_handler(
                handle_edited_message,
                events.MessageEdited(chats=active_channels["source"])
            )
            
            # Log after adding
            logger.info(f"After adding handlers, event handlers: {len(user_client._event_builders) if hasattr(user_client, '_event_builders') else 0}")
        else:
            logger.warning("No source channels configured, event handlers not registered")
    else:
        logger.warning("User client not available or not connected, skipping event handler update")

async def save_tag_config():
    """Save current tag replacement configuration to environment variable and .env file"""
    tag_config_json = json.dumps(tag_replacements)
    os.environ["TAG_CONFIG"] = tag_config_json
    
    # Update the .env file to persist the configuration
    try:
        # Read the current .env file
        with open(".env", "r") as env_file:
            env_content = env_file.read()
        
        # Check if TAG_CONFIG already exists in the file
        if "TAG_CONFIG=" in env_content:
            # Replace existing value
            new_env_content = re.sub(
                r'TAG_CONFIG=.*', 
                f'TAG_CONFIG=\'{tag_config_json}\'', 
                env_content
            )
        else:
            # Add new entry
            new_env_content = env_content + f'\nTAG_CONFIG=\'{tag_config_json}\''
        
        # Write back to .env file
        with open(".env", "w") as env_file:
            env_file.write(new_env_content)
            
        logger.info(f"Updated tag configuration in .env file and memory: {tag_config_json}")
    except Exception as e:
        logger.error(f"Failed to update .env file with tag configuration: {str(e)}")
        logger.info(f"Updated tag configuration in memory only: {tag_config_json}")
    
async def save_admin_config():
    """Save current admin users configuration to environment variable and .env file"""
    admin_config_json = json.dumps(ADMIN_USERS)
    os.environ["ADMIN_USERS"] = admin_config_json
    
    # Update the .env file to persist the configuration
    try:
        # Read the current .env file
        with open(".env", "r") as env_file:
            env_content = env_file.read()
        
        # Check if ADMIN_USERS already exists in the file
        if "ADMIN_USERS=" in env_content:
            # Replace existing value
            new_env_content = re.sub(
                r'ADMIN_USERS=.*', 
                f'ADMIN_USERS=\'{admin_config_json}\'', 
                env_content
            )
        else:
            # Add new entry
            new_env_content = env_content + f'\nADMIN_USERS=\'{admin_config_json}\''
        
        # Write back to .env file
        with open(".env", "w") as env_file:
            env_file.write(new_env_content)
            
        logger.info(f"Updated admin users configuration in .env file and memory: {admin_config_json}")
    except Exception as e:
        logger.error(f"Failed to update .env file with admin users configuration: {str(e)}")
        logger.info(f"Updated admin users configuration in memory only: {admin_config_json}")


async def update_farewell_sticker_constant(sticker_id: str, add_to_list: bool = True) -> bool:
    """
    Update the farewell sticker constants in assets/stickers/constants.py
    
    Args:
        sticker_id: The new sticker ID to set
        add_to_list: If True, add to the sticker list; if False, replace entire list with this sticker
        
    Returns:
        bool: True if the update was successful, False otherwise
    """
    try:
        constants_path = "assets/stickers/constants.py"
        
        # Make sure the directory exists
        os.makedirs(os.path.dirname(constants_path), exist_ok=True)
        
        # Get current stickers list
        current_stickers = FAREWELL_STICKERS.copy()
        
        # Add new sticker to the list
        if add_to_list and sticker_id not in current_stickers:
            current_stickers.append(sticker_id)
        elif not add_to_list:
            # Replace list with just this sticker
            current_stickers = [sticker_id]
        
        # Format the stickers list as a Python list with proper indentation
        stickers_str = "[\n"
        for s in current_stickers:
            stickers_str += f'    "{s}",\n'
        stickers_str += "]"
        
        # Read the current content of the file
        if os.path.exists(constants_path):
            with open(constants_path, "r") as f:
                content = f.read()
                
            # Use regex to replace the stickers list
            if "FAREWELL_STICKERS" in content:
                # Replace the existing stickers list
                new_content = re.sub(
                    r'FAREWELL_STICKERS\s*=\s*\[(.*?)\]',
                    f'FAREWELL_STICKERS = {stickers_str}',
                    content,
                    flags=re.DOTALL  # Match across multiple lines
                )
                
                # Now update the backward compatibility variable
                new_content = re.sub(
                    r'FAREWELL_STICKER_ID\s*=\s*FAREWELL_STICKERS\[[^\]]*\].*',
                    f'FAREWELL_STICKER_ID = FAREWELL_STICKERS[0] if FAREWELL_STICKERS else ""',
                    new_content
                )
                
                # Write the updated content back to the file
                with open(constants_path, "w") as f:
                    f.write(new_content)
            else:
                # The variable doesn't exist, so create a new file with both constants
                with open(constants_path, "w") as f:
                    f.write('"""\nConstants for stickers used by the bot\n"""\n\n')
                    f.write(f'# List of farewell stickers used when leaving a channel after purging\n')
                    f.write(f'# The bot will randomly choose one from this list each time\n')
                    f.write(f'FAREWELL_STICKERS = {stickers_str}\n\n')
                    f.write(f'# Backward compatibility - first sticker in the list\n')
                    f.write(f'FAREWELL_STICKER_ID = FAREWELL_STICKERS[0] if FAREWELL_STICKERS else ""\n')
        else:
            # Create a new constants.py file
            with open(constants_path, "w") as f:
                f.write('"""\nConstants for stickers used by the bot\n"""\n\n')
                f.write(f'# List of farewell stickers used when leaving a channel after purging\n')
                f.write(f'# The bot will randomly choose one from this list each time\n')
                f.write(f'FAREWELL_STICKERS = {stickers_str}\n\n')
                f.write(f'# Backward compatibility - first sticker in the list\n')
                f.write(f'FAREWELL_STICKER_ID = FAREWELL_STICKERS[0] if FAREWELL_STICKERS else ""\n')
                
        logger.info(f"Successfully updated farewell stickers list in constants.py")
        logger.info(f"Current stickers count: {len(current_stickers)}")
        return True
        
    except Exception as e:
        logger.error(f"Error updating farewell sticker constants: {str(e)}")
        return False

# Function to find and replace channel tags in message text
async def find_replace_channel_tags(text: str, entities=None, clean_mode=False) -> Tuple[str, List[Dict]]:
    # Log the input for debugging
    logger.info(f"DEBUGGING TAG REPLACEMENT - Input text: {text[:100]}...")
    """
    Find and replace channel tags in message text
    Returns: (modified_text, [{'old_offset': int, 'new_offset': int, 'entity': Entity}])

    Parameters:
    - text: The message text to process
    - entities: Optional list of message entities 
    - clean_mode: If True, tries to remove all channel attributions instead of replacing them
    """
    if not text:
        return text, []
    
    # Get destination channel tag if available
    destination_tag = None
    destination_link = None
    destination_name = None
    
    if active_channels["destination"]:
        try:
            # Try to get destination channel info to obtain username and other details
            if user_client:
                dest_info = await get_entity_info(user_client, active_channels["destination"])
                if dest_info:
                    if dest_info.get("username"):
                        destination_tag = f"@{dest_info['username']}"
                        destination_link = f"t.me/{dest_info['username']}"
                    destination_name = dest_info.get("title")
        except Exception as e:
            logger.error(f"Error getting destination channel info: {str(e)}")
    
    # If no custom replacements are defined and no destination channel info is available,
    # and we're not in clean mode, we can't perform any replacements
    if not tag_replacements and not destination_tag and not clean_mode:
        return text, []

    entity_adjustments = []
    
    # Handle direct mentions (@channel_name)
    modified_text = text
    offset_adjustment = 0
    
    # Find all @mentions in the text using regex
    mention_pattern = r'@([a-zA-Z0-9_]+)'
    for match in re.finditer(mention_pattern, text):
        mention = match.group(0)  # The full mention including @
        replacement = None
        
        # Check if we have a specific replacement for this mention
        if mention in tag_replacements:
            replacement = tag_replacements[mention]
        # If no specific replacement but we have a destination channel, use its tag
        elif destination_tag and mention != destination_tag:
            # In clean mode, we might remove the mention completely
            if clean_mode:
                replacement = ""  # Remove completely
            else:
                replacement = destination_tag
        # If clean mode and no replacement, remove this mention
        elif clean_mode:
            replacement = ""
            
        # Only proceed if we have a replacement or we're explicitly removing it
        if replacement is not None:  # This checks for both replacements and empty string
            start_pos = match.start() + offset_adjustment
            end_pos = match.end() + offset_adjustment
            
            # Replace the mention in the modified text
            modified_text = modified_text[:start_pos] + replacement + modified_text[end_pos:]
            
            # Calculate the adjustment for future replacements
            old_length = len(mention)
            new_length = len(replacement)
            length_diff = new_length - old_length
            offset_adjustment += length_diff
            
            # Record entity adjustments for any entities that come after this match
            entity_adjustments.append({
                'position': end_pos,
                'adjustment': length_diff
            })

    # Handle all possible t.me links with a comprehensive approach
    # Pattern 1: Standard t.me links with protocol variants
    tme_pattern1 = r'\b(?:https?:\/\/)?(?:t\.me|telegram\.me)\/([a-zA-Z0-9_]+)(?:\/[^?\s]*)?(?:\?[^\s]*)?\b'
    # Pattern 2: Markdown-style links [text](t.me/link)
    tme_pattern2 = r'\[([^\]]+)\]\((?:https?:\/\/)?(?:t\.me|telegram\.me)\/([a-zA-Z0-9_]+)(?:\/[^?\s]*)?(?:\?[^\s]*)?\)'
    # Pattern 3: t.me/joinchat or t.me/+ links
    tme_pattern3 = r'\b(?:https?:\/\/)?(?:t\.me|telegram\.me)\/(?:joinchat\/|\+)([a-zA-Z0-9_\-]+)(?:\/[^?\s]*)?(?:\?[^\s]*)?\b'
    # Pattern 4: Markdown links with joinchat
    tme_pattern4 = r'\[([^\]]+)\]\((?:https?:\/\/)?(?:t\.me|telegram\.me)\/(?:joinchat\/|\+)([a-zA-Z0-9_\-]+)(?:\/[^?\s]*)?(?:\?[^\s]*)?\)'
    
    # Collect all matches
    tme_matches = []
    tme_matches.extend(list(re.finditer(tme_pattern1, text)))
    tme_matches.extend(list(re.finditer(tme_pattern2, text)))
    tme_matches.extend(list(re.finditer(tme_pattern3, text)))
    tme_matches.extend(list(re.finditer(tme_pattern4, text)))
    
    # Aggressively add more fallback patterns
    # Pattern 5: Anything that looks remotely like a t.me link
    tme_pattern5 = r'\bt\.me\/[^\s]+'
    tme_matches.extend(list(re.finditer(tme_pattern5, text)))
    
    # Sort matches by start position to handle them in order
    tme_matches.sort(key=lambda m: m.start())
    
    # Log all matches for debugging
    logger.info(f"Found {len(tme_matches)} potential t.me links in message")
    for i, match in enumerate(tme_matches):
        logger.info(f"  Match {i+1}: {match.group(0)}")
    
    # Keep track of which matches are within hyperlink entities to avoid direct replacement
    skip_positions = []
    
    # Check if any t.me links are within hyperlink entities
    if entities:
        for entity in entities:
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                entity_start = entity.offset
                entity_end = entity.offset + entity.length
                
                # Check if any t.me match falls within this entity
                for match in tme_matches:
                    match_start = match.start()
                    match_end = match.end()
                    
                    if entity_start <= match_start and match_end <= entity_end:
                        # This match is within a hyperlink, mark to skip direct text replacement
                        skip_positions.append((match_start, match_end))
                        logger.info(f"Skipping direct replacement for t.me link in hyperlink: {match.group(0)}")
    
    # Process t.me links that are not within hyperlink entities
    for match in tme_matches:
        match_start = match.start()
        match_end = match.end()
        
        # Skip if this match is within a hyperlink (will be handled by entity processing)
        if any(start <= match_start and match_end <= end for start, end in skip_positions):
            continue
            
        # Get the full link match
        tme_full_link = match.group(0)
        logger.info(f"Processing t.me link: {tme_full_link}")
        
        # Extract username from the appropriate capture group based on the match pattern
        is_markdown_link = False
        username = None
        
        # Determine if this is a markdown link and extract the right username
        if '[' in tme_full_link and '](' in tme_full_link:
            is_markdown_link = True
            # This is likely a markdown link, extract differently
            try:
                # For markdown links with format [text](url)
                if len(match.groups()) > 1:
                    visible_text = match.group(1)  # The text in [text]
                    username = match.group(2)  # Extract username
                    logger.info(f"Markdown link: text='{visible_text}', username='{username}'")
                else:
                    # Fallback - try to extract manually
                    link_parts = tme_full_link.split('](')[1].rstrip(')')
                    if 't.me/' in link_parts:
                        username = link_parts.split('t.me/')[1].split('/')[0].split('?')[0]
                        logger.info(f"Fallback extracted username: {username}")
            except Exception as e:
                logger.error(f"Error parsing markdown link: {str(e)}")
        else:
            # Standard t.me link
            try:
                # Try to match groups from standard patterns
                if len(match.groups()) >= 1:
                    username = match.group(1)  # Regular capture
                else:
                    # Fallback - extract username from the URL
                    if 't.me/' in tme_full_link:
                        username = tme_full_link.split('t.me/')[1].split('/')[0].split('?')[0]
                    elif 'telegram.me/' in tme_full_link:
                        username = tme_full_link.split('telegram.me/')[1].split('/')[0].split('?')[0]
            except Exception as e:
                logger.error(f"Error extracting username from link: {str(e)}")
                
        # Ensure we got something
        if not username:
            logger.warning(f"Could not extract username from link: {tme_full_link}")
            continue  # Skip to next match
            
        # Clean up username - remove any remaining path parts or parameters
        username = username.split('/')[0].split('?')[0]
        logger.info(f"Final extracted username: '{username}'")
        
        # Parse the link to preserve path, query parameters, and determine format
        has_prefix = tme_full_link.startswith('http')
        has_path_or_query = '/' in tme_full_link[tme_full_link.index(username) + len(username):] if username in tme_full_link else False
        query_part = ''
        path_suffix = ''
        
        # Extract path suffix and query parameters if they exist
        remaining = tme_full_link[tme_full_link.index(username) + len(username):]
        if remaining:
            if '?' in remaining:
                path_query = remaining.split('?', 1)
                path_suffix = path_query[0]
                query_part = '?' + path_query[1] if path_query[1] else ''
            else:
                path_suffix = remaining
        
        # Log what we extracted for debugging
        logger.info(f"Extracted non-entity t.me link: '{tme_full_link}', username: '{username}'")
        if path_suffix or query_part:
            logger.info(f"With path: '{path_suffix}', query: '{query_part}'")
        
        replacement = None
        
        # Check if we have a specific replacement for this exact link
        if tme_full_link in tag_replacements:
            replacement = tag_replacements[tme_full_link]
        # Also check for the base version without path/query
        elif f"t.me/{username}" in tag_replacements:
            base_replacement = tag_replacements[f"t.me/{username}"]
            # Add back path and query if appropriate
            if has_path_or_query and not ('/' in base_replacement or '?' in base_replacement):
                replacement = base_replacement + path_suffix + query_part
            else:
                replacement = base_replacement
        # Check for @username format in tag_replacements
        elif f"@{username}" in tag_replacements:
            mention_replacement = tag_replacements[f"@{username}"]
            # If replacement is @username format, convert to t.me format
            if mention_replacement.startswith('@'):
                replacement_username = mention_replacement[1:]
                # Reconstruct with the appropriate format matching the original
                if has_prefix:
                    replacement = f"https://t.me/{replacement_username}{path_suffix}{query_part}"
                else:
                    replacement = f"t.me/{replacement_username}{path_suffix}{query_part}"
            else:
                # If replacement is already in t.me format, use it directly
                replacement = mention_replacement
        # If no specific replacement but we have a destination channel, use it
        elif destination_tag and f"@{username}" != destination_tag:
            if clean_mode:
                # In clean mode, try to remove the channel link entirely
                # This might be a more complex decision depending on the context
                replacement = ""
            else:
                # Convert @username to t.me/username format preserving path and query
                dest_username = destination_tag[1:]  # Remove the @ symbol
                if has_prefix:
                    replacement = f"https://t.me/{dest_username}{path_suffix}{query_part}"
                else:
                    replacement = f"t.me/{dest_username}{path_suffix}{query_part}"
        # If we're in clean mode and didn't find a specific replacement
        elif clean_mode:
            # Remove the link completely
            replacement = ""
            
        # Only proceed if we have a replacement
        if replacement:
            start_pos = match_start + offset_adjustment
            end_pos = match_end + offset_adjustment
            
            # Special handling for markdown style links [text](url)
            if is_markdown_link:
                visible_text = match.group(1)
                
                # Determine if the replacement should preserve the markdown format
                # If replacement is already a full URL or t.me link, wrap it in markdown
                if replacement.startswith('http') or replacement.startswith('t.me/'):
                    final_replacement = f"[{visible_text}]({replacement})"
                # If replacement is a mention (@username), just use it directly
                elif replacement.startswith('@'):
                    final_replacement = replacement
                # For empty replacements (clean mode), just use the visible text
                elif replacement == "":
                    final_replacement = visible_text
                else:
                    # Default case - try to preserve markdown format
                    final_replacement = f"[{visible_text}]({replacement})"
                    
                logger.info(f"Replacing markdown link '{match.group(0)}' with '{final_replacement}'")
                replacement = final_replacement
            
            # Replace the link in the modified text
            modified_text = modified_text[:start_pos] + replacement + modified_text[end_pos:]
            
            # Calculate the adjustment for future replacements
            old_length = len(tme_full_link)
            new_length = len(replacement)
            length_diff = new_length - old_length
            offset_adjustment += length_diff
            
            # Record entity adjustments for any entities that come after this match
            entity_adjustments.append({
                'position': end_pos,
                'adjustment': length_diff
            })
    
    # Process entities if provided
    processed_entities = []
    if entities:
        for entity in entities:
            # Create a copy of the entity
            entity_dict = {
                'type': type(entity).__name__,
                'offset': entity.offset,
                'length': entity.length,
                'url': getattr(entity, 'url', None)
            }
            
            # Adjust the offset based on previous replacements
            adjustment = 0
            for adj in entity_adjustments:
                if entity.offset >= adj['position']:
                    adjustment += adj['adjustment']
            
            # Also check if the entity itself is a mention that needs replacing
            if isinstance(entity, MessageEntityMention):
                mention_text = text[entity.offset:entity.offset + entity.length]
                
                replacement = None
                if mention_text in tag_replacements:
                    replacement = tag_replacements[mention_text]
                elif destination_tag and mention_text != destination_tag:
                    replacement = destination_tag
                    
                if replacement:
                    # The entity itself is a mention that was replaced
                    entity_dict['length'] = len(replacement)
            
            # Check if the entity is a URL that needs replacing
            if isinstance(entity, (MessageEntityTextUrl, MessageEntityUrl)):
                if isinstance(entity, MessageEntityTextUrl):
                    # Handle t.me links
                    if entity.url.startswith('https://t.me/') or entity.url.startswith('http://t.me/') or entity.url.startswith('t.me/'):
                        # Standardize URL format for processing
                        if entity.url.startswith('https://'):
                            clean_url = entity.url[8:]  # Remove https://
                        elif entity.url.startswith('http://'):
                            clean_url = entity.url[7:]  # Remove http://
                        else:
                            clean_url = entity.url
                        
                        # Extract username part and handle possible path components
                        parts = clean_url.split('/', 1)
                        if len(parts) > 1 and parts[0] == 't.me':
                            username_part = parts[1].split('/', 1)[0]  # Get just the username without additional path
                            path_suffix = parts[1].split('/', 1)[1] if '/' in parts[1] else ""
                        else:
                            username_part = clean_url[5:] if clean_url.startswith('t.me/') else ""
                            path_suffix = ""
                            
                        # Log what we extracted for debugging
                        logger.info(f"Extracted username: '{username_part}' from URL: {entity.url}")
                        if path_suffix:
                            logger.info(f"URL has additional path: '{path_suffix}'")
                        
                        # Check for replacement
                        replacement = None
                        
                        # Get the visible link text which may be the same as the username (causing "LlLl" duplication)
                        link_text = text[entity.offset:entity.offset + entity.length]
                        logger.info(f"Processing hyperlink text='{link_text}', username_part='{username_part}', url={entity.url}")
                        
                        # Check if this hyperlink's visible text matches username (causing "LlLl" duplication)
                        text_matches_username = False
                        if link_text.lower() == username_part.lower():
                            text_matches_username = True
                            logger.info(f"Text '{link_text}' matches username '{username_part}' - will only change URL, not text")
                        
                        # Try different formats for lookup
                        tme_full = f"t.me/{username_part}"
                        tme_https = f"https://t.me/{username_part}"
                        mention_format = f"@{username_part}"
                        
                        # Check exact matches first
                        if entity.url in tag_replacements:
                            replacement = tag_replacements[entity.url]
                        elif tme_full in tag_replacements:
                            replacement = tag_replacements[tme_full]
                        elif tme_https in tag_replacements:
                            replacement = tag_replacements[tme_https]
                        elif mention_format in tag_replacements:
                            mention_replacement = tag_replacements[mention_format]
                            # Convert from @username to t.me format if needed
                            if mention_replacement.startswith('@'):
                                replacement = f"https://t.me/{mention_replacement[1:]}"
                            else:
                                replacement = mention_replacement
                        # Always replace with destination tag when appropriate
                        elif destination_tag:
                            # Always use the destination tag for replacement
                            # But skip if the channel is already the destination channel
                            if mention_format != destination_tag:
                                dest_username = destination_tag[1:]  # Remove the @ symbol
                                
                                # Preserve the original path suffix if it exists
                                if path_suffix:
                                    replacement = f"https://t.me/{dest_username}/{path_suffix}"
                                else:
                                    replacement = f"https://t.me/{dest_username}"
                                
                                logger.info(f"Using destination tag {destination_tag} for replacement of {mention_format}")
                        
                        # Apply replacement if found
                        if replacement:
                            # Ensure proper https:// prefix
                            if not replacement.startswith('https://') and not replacement.startswith('http://'):
                                if replacement.startswith('t.me/'):
                                    replacement = f"https://{replacement}"
                                else:
                                    replacement = f"https://t.me/{replacement.replace('@', '')}"
                            
                            # ENHANCED HANDLING FOR TEXT DUPLICATION ISSUES
                            # If the visible text matches the channel name, we need special handling
                            if text_matches_username:
                                logger.info(f"Fixing duplication issue: Only changing URL, keeping text '{link_text}'")
                                entity_dict['url'] = replacement
                                # Don't change the text, just update URL in entity to avoid duplication
                                
                                # Extract destination username from replacement URL
                                dest_username = ""
                                if 't.me/' in replacement:
                                    try:
                                        dest_username = replacement.split('t.me/')[1].split('/')[0]
                                        logger.info(f"Extracted destination username: {dest_username}")
                                    except Exception as e:
                                        logger.error(f"Error extracting destination username: {e}")
                                
                                # If the link text contains the original username and would be replaced,
                                # we need to prevent duplication by NOT duplicating the text
                                if dest_username and dest_username.lower() in link_text.lower():
                                    logger.info(f"Special case: Link text already contains destination name. Using original text.")
                                    # Keep original text to prevent duplication
                            else:
                                # Normal case - not a duplication issue
                                logger.info(f"Replacing URL: {entity.url} → {replacement}")
                                entity_dict['url'] = replacement
                                
                            # Log full entity details for debugging
                            logger.info(f"Hyperlink text: '{link_text}', Original URL: {entity.url}, New URL: {replacement}")
            
            entity_dict['offset'] += adjustment
            processed_entities.append(entity_dict)
    
    return modified_text, processed_entities

async def detect_markdown_links(text):
    """
    Detect markdown style links in text of format [text](url)
    Returns a list of entities and the updated text with any replacements
    """
    
    # Enhanced pattern for markdown-style links: [text](url) including t.me links
    # This pattern catches both http and https links as well as t.me links without protocol
    pattern = r'\[([^\]]+)\]\((?:https?://)?(?:[^)]+)\)'
    
    # Find all markdown links
    markdown_links = list(re.finditer(pattern, text))
    
    if not markdown_links:
        return text, []
    
    # We'll create TextUrl entities for these links
    entities = []
    
    # First, collect all the links and their positions
    links_to_process = []
    for match in markdown_links:
        # Extract the link text and URL
        link_text = match.group(1)
        # Extract the URL part, which is now in a different position due to pattern change
        # The URL is everything between the () parentheses
        full_match = match.group(0)
        url_start = full_match.index('(') + 1
        url_end = full_match.rindex(')')
        link_url = full_match[url_start:url_end]
        
        # Make sure t.me links have a proper protocol
        if link_url.startswith('t.me/') or link_url.startswith('telegram.me/'):
            link_url = 'https://' + link_url
            
        logger.info(f"Extracted markdown link: text='{link_text}', url='{link_url}'")
        
        links_to_process.append({
            'start': match.start(),
            'end': match.end(),
            'text': link_text,
            'url': link_url,
            'full_match': match.group(0)
        })
    
    # Sort them from end to start to avoid offset issues
    links_to_process.sort(key=lambda x: x['start'], reverse=True)
    
    # Process each link
    modified_text = text
    for link in links_to_process:
        # Create entity for this link
        entity = {
            'type': 'MessageEntityTextUrl',
            'offset': link['start'],
            'length': len(link['text']),
            'url': link['url']
        }
        
        entities.append(entity)
        
        # Replace the markdown link with just the text
        modified_text = modified_text[:link['start']] + link['text'] + modified_text[link['end']:]
    
    # Log the transformation for debugging
    logger.info(f"Markdown transformation: '{text}' → '{modified_text}'")
    logger.info(f"Generated {len(entities)} entities from markdown links")
    
    # Return the entities in correct order (from start to end)
    entities.sort(key=lambda x: x['offset'])
    
    # Recalculate offsets based on transformations
    offset_adjustment = 0
    for i, entity in enumerate(entities):
        entity['offset'] += offset_adjustment
        # Calculate adjustment for next entities
        original_length = len(links_to_process[len(links_to_process) - 1 - i]['full_match'])
        new_length = len(links_to_process[len(links_to_process) - 1 - i]['text'])
        offset_adjustment -= (original_length - new_length)
    
    return modified_text, entities

async def direct_replace_tme_links(text: str) -> str:
    """Directly replace t.me links in text without using regex - fallback method"""
    if not text:
        return text
        
    # Get destination channel tag
    destination_tag = None
    if active_channels["destination"]:
        try:
            if user_client:
                dest_info = await get_entity_info(user_client, active_channels["destination"])
                if dest_info and dest_info.get("username"):
                    destination_tag = f"@{dest_info['username']}"
        except Exception as e:
            logger.error(f"Error getting destination in direct replace: {str(e)}")
    
    # If no destination tag, create a fallback one
    if not destination_tag and active_channels["destination"]:
        # Create a fallback destination tag
        destination_tag = f"@destination{abs(int(active_channels['destination']))}"  
    
    if not destination_tag:
        # If we still don't have a destination tag, we can't replace anything
        return text
        
    logger.info(f"Using destination tag: {destination_tag} for direct replacements")
    
    # Direct string replacement for t.me links (multiple formats)
    modified = text
    
    # List all formats to check
    patterns_to_check = [
        "t.me/",
        "https://t.me/",
        "http://t.me/",
        "telegram.me/",
        "https://telegram.me/",
        "http://telegram.me/"
    ]
    
    # Destination replacements
    dest_username = destination_tag[1:]  # Remove @ from @username
    replacements = {
        "t.me/": f"t.me/{dest_username}",
        "https://t.me/": f"https://t.me/{dest_username}",
        "http://t.me/": f"http://t.me/{dest_username}",
        "telegram.me/": f"telegram.me/{dest_username}",
        "https://telegram.me/": f"https://telegram.me/{dest_username}",
        "http://telegram.me/": f"http://telegram.me/{dest_username}"
    }
    
    # Log the text we're processing
    logger.info(f"DIRECT TG LINK REPLACEMENT - processing text: {text[:100]}...")
    
    # Check for each pattern
    for pattern in patterns_to_check:
        if pattern in modified:
            # Found a potential match - now we need to handle it correctly
            logger.info(f"Found potential match for {pattern} in text")
            
            # Split the text by the pattern to find all occurrences
            segments = modified.split(pattern)
            
            if len(segments) > 1:
                result = segments[0]  # Start with the first segment
                
                # For each remaining segment, prepend our replacement pattern
                # but only replace the username part, not any path or query parameters
                for i in range(1, len(segments)):
                    segment = segments[i]
                    
                    # Extract the original username (everything up to /, ? or space)
                    username_end = min(
                        segment.find('/') if segment.find('/') >= 0 else len(segment),
                        segment.find('?') if segment.find('?') >= 0 else len(segment),
                        segment.find(' ') if segment.find(' ') >= 0 else len(segment)
                    )
                    
                    original_username = segment[:username_end]
                    rest_of_segment = segment[username_end:]
                    
                    # Only do the replacement if this is a valid username and not part of a longer word
                    if original_username and (original_username.isalnum() or '_' in original_username):
                        # Use our replacement instead of the original username
                        logger.info(f"Replacing {pattern}{original_username} with {replacements[pattern]}")
                        result += replacements[pattern] + rest_of_segment
                    else:
                        # If it doesn't look like a username, leave it as is
                        result += pattern + segment
                    
                modified = result
    
    # Check if any replacements were made
    if modified != text:
        logger.info(f"DIRECT TG LINK REPLACEMENT - result: {modified[:100]}...")
    else:
        logger.info("No direct t.me link replacements made")
    
    return modified

async def process_message_for_reposting(message: Message) -> Dict[str, Any]:
    # Debug logging for message content
    logger.info(f"PROCESSING SOURCE MESSAGE: {message.id} for reposting")
    """
    Process a message for reposting, including handling channel tag replacements
    Returns a dict with the processed message attributes
    """
    # Extract basic message info
    msg_data = {
        "text": message.text if message.text else "",
        "entities": message.entities if hasattr(message, 'entities') else None,
        "has_media": False,
        "media_data": None,
        "file_path": None
    }
    
    # Check for markdown-style links in the text
    if msg_data["text"]:
        # First look for markdown links [text](url) and convert to entities
        processed_text, markdown_entities = await detect_markdown_links(msg_data["text"])
        
        if markdown_entities:
            # We found markdown-style links
            logger.info(f"Detected {len(markdown_entities)} markdown-style links in text")
            msg_data["text"] = processed_text
            
            # Combine existing entities with the markdown entities we found
            if msg_data["entities"]:
                # Sort all entities by offset
                combined_entities = list(msg_data["entities"]) + [
                    MessageEntityTextUrl(
                        offset=e['offset'],
                        length=e['length'],
                        url=e['url']
                    ) for e in markdown_entities
                ]
                combined_entities.sort(key=lambda e: e.offset)
                msg_data["entities"] = combined_entities
            else:
                # Only markdown entities
                msg_data["entities"] = [
                    MessageEntityTextUrl(
                        offset=e['offset'],
                        length=e['length'],
                        url=e['url']
                    ) for e in markdown_entities
                ]
    
    # Process channel tag replacements
    if msg_data["text"]:
        # First try direct t.me link replacement for higher reliability
        direct_processed_text = await direct_replace_tme_links(msg_data["text"])
        
        # If direct replacement made changes, use that text instead
        if direct_processed_text != msg_data["text"]:
            logger.info("Using direct t.me link replacement results")
            msg_data["text"] = direct_processed_text
        
        # Now continue with normal channel tag replacements
        use_clean_mode = BOT_CONFIG.get("CLEAN_MODE", "false").lower() == "true"
        modified_text, processed_entities = await find_replace_channel_tags(
            msg_data["text"], 
            msg_data["entities"],
            clean_mode=use_clean_mode
        )
        msg_data["text"] = modified_text
        
        # Convert processed entities back to Telegram entities
        if processed_entities:
            # Log what we're processing for debugging
            logger.info(f"Processing {len(processed_entities)} entities for message")
            
            # For text with hyperlinks, we'll also create a formatted HTML version as a backup
            formatted_html = msg_data["text"]
            
            new_entities = []
            for entity_dict in processed_entities:
                entity_type = entity_dict['type']
                
                # Generate formatted HTML version for hyperlinks
                if entity_type == 'MessageEntityTextUrl' and entity_dict['url']:
                    # Get the text that should be hyperlinked
                    start = entity_dict['offset']
                    end = start + entity_dict['length']
                    if 0 <= start < len(modified_text) and 0 < end <= len(modified_text):
                        display_text = modified_text[start:end]
                        
                        # Format it as HTML
                        html_link = f'<a href="{entity_dict["url"]}">{display_text}</a>'
                        
                        # Log what we're creating
                        logger.info(f"Creating HTML link: {html_link} for text '{display_text}'")
                
                # Create the entity object
                if entity_type == 'MessageEntityTextUrl':
                    entity = MessageEntityTextUrl(
                        offset=entity_dict['offset'],
                        length=entity_dict['length'],
                        url=entity_dict['url']
                    )
                elif entity_type == 'MessageEntityUrl':
                    entity = MessageEntityUrl(
                        offset=entity_dict['offset'],
                        length=entity_dict['length']
                    )
                elif entity_type == 'MessageEntityMention':
                    entity = MessageEntityMention(
                        offset=entity_dict['offset'],
                        length=entity_dict['length']
                    )
                else:
                    # Skip other entity types that we can't recreate
                    continue
                
                new_entities.append(entity)
            
            msg_data["entities"] = new_entities
            
            # Always use HTML backup to ensure proper rendering of links
            msg_data["html_backup"] = True

    # Handle media content
    if message.media:
        # Special case: Check if this is actually just text with a web URL
        # This is to fix the issue where hyperlinks are detected as media files
        is_web_page = False
        try:
            # Check if the media is a webpage preview (MessageMediaWebPage)
            if hasattr(message.media, 'webpage') and message.media.webpage:
                logger.info("Detected webpage preview in message")
                is_web_page = True
                
                # If it's a webpage preview, we should treat it as a text message
                # with hyperlinks, not as media
                if msg_data["text"]:
                    logger.info("Message has text and webpage preview - treating as text message")
                    
                    # Make sure HTML backup is enabled for these messages
                    if msg_data["entities"]:
                        msg_data["html_backup"] = True
                        
                    # Don't mark as media to prevent file creation
                    msg_data["has_media"] = False
                    return msg_data
        except Exception as e:
            logger.error(f"Error checking for webpage media: {str(e)}")
            
        # If we get here, it's a regular media message
        logger.info(f"Processing media message: {message.id} in chat: {message.chat_id}")
        msg_data["has_media"] = True
        
        # Determine media type from attributes
        media_type = "unknown"
        is_photo = False
        is_video = False
        is_gif = False
        is_sticker = False
        is_voice = False
        is_audio = False
        is_document = False
        
        try:
            # Handle photos
            if isinstance(message.media, MessageMediaPhoto):
                media_type = "photo"
                is_photo = True
            
            # Handle documents and other media types
            elif isinstance(message.media, MessageMediaDocument):
                # Extract document attributes
                document = message.media.document
                mime_type = document.mime_type if hasattr(document, 'mime_type') else "application/octet-stream"
                file_name = None
                
                # Get file attributes
                for attr in document.attributes:
                    # Check for filename
                    if hasattr(attr, 'file_name') and attr.file_name:
                        file_name = attr.file_name
                    
                    # Determine media type
                    if hasattr(attr, 'round_message') and attr.round_message:
                        media_type = "round"  # Round video (video message)
                        is_video = True
                    elif hasattr(attr, 'video') and attr.video:
                        if mime_type == "video/mp4" and hasattr(attr, 'duration') and attr.duration <= 15:
                            # This might be a GIF-like video
                            if any(hasattr(a, 'animated') and a.animated for a in document.attributes):
                                media_type = "gif"
                                is_gif = True
                            else:
                                media_type = "video"
                                is_video = True
                        else:
                            media_type = "video"
                            is_video = True
                    elif hasattr(attr, 'voice') and attr.voice:
                        media_type = "voice"
                        is_voice = True
                    elif hasattr(attr, 'audio') and attr.audio:
                        media_type = "audio"
                        is_audio = True
                    elif mime_type.startswith("audio/"):
                        media_type = "audio"
                        is_audio = True
                    elif mime_type.startswith("video/"):
                        media_type = "video"
                        is_video = True
                    elif mime_type.startswith("image/"):
                        if mime_type == "image/webp" or mime_type == "image/gif":
                            media_type = "sticker"
                            is_sticker = True
                        else:
                            media_type = "photo"
                            is_photo = True
                
                # If we still haven't determined a type, use mime_type
                if media_type == "unknown":
                    if mime_type.startswith("image/"):
                        media_type = "photo"
                        is_photo = True
                    elif mime_type.startswith("video/"):
                        media_type = "video"
                        is_video = True
                    elif mime_type.startswith("audio/"):
                        media_type = "audio"
                        is_audio = True
                    else:
                        media_type = "document"
                        is_document = True
                
                # Store document attributes
                msg_data["document_attributes"] = document.attributes if hasattr(document, 'attributes') else []
            
            # Handle web pages and other media types
            elif isinstance(message.media, MessageMediaWebPage):
                # Critical fix: This isn't really media - it's text with links
                # This is a message with a URL that Telegram has auto-generated a preview for
                logger.info("Detected message with webpage preview - handling as text with hyperlinks")
                
                # Webpage previews should be handled as regular messages, not as media
                # We'll still process the preview info, but we won't download anything
                
                # IMPORTANT: We need to modify has_media to prevent file download
                msg_data["has_media"] = False
                
                # For web pages, we still need to handle the rich preview content
                webpage = message.media.webpage
                
                # If this is a Telegram channel preview or similar rich content
                has_webpage_content = False
                
                if hasattr(webpage, 'type') and webpage.type:
                    media_type = f"webpage_{webpage.type}"
                    logger.info(f"Webpage type: {webpage.type}")
                    has_webpage_content = True
                
                if hasattr(webpage, 'site_name') and webpage.site_name:
                    # Store the site name for reference
                    msg_data["webpage_site_name"] = webpage.site_name
                    logger.info(f"Webpage site name: {webpage.site_name}")
                    has_webpage_content = True
                    
                if hasattr(webpage, 'title') and webpage.title:
                    # Store the title
                    msg_data["webpage_title"] = webpage.title
                    logger.info(f"Webpage title: {webpage.title}")
                    has_webpage_content = True
                
                if hasattr(webpage, 'description') and webpage.description:
                    # Store the description
                    msg_data["webpage_description"] = webpage.description
                    logger.info(f"Webpage description: {webpage.description}")
                    has_webpage_content = True
                
                if hasattr(webpage, 'url') and webpage.url:
                    # Store the URL - this is especially important for the tag replacement to work
                    msg_data["webpage_url"] = webpage.url
                    logger.info(f"Webpage URL: {webpage.url}")
                    has_webpage_content = True
                    
                    # Make sure HTML backup is enabled for these messages
                    msg_data["html_backup"] = True
                    
                    # Check if this URL should be replaced according to our tag rules
                    replaced_url = None
                    if webpage.url in tag_replacements:
                        replaced_url = tag_replacements[webpage.url]
                    else:
                        # Check if the URL contains a channel username that should be replaced
                        for old_tag, new_tag in tag_replacements.items():
                            if old_tag.startswith('@') and f"t.me/{old_tag[1:]}" in webpage.url:
                                # Replace t.me/username with our replacement
                                new_username = new_tag[1:] if new_tag.startswith('@') else new_tag
                                replaced_url = webpage.url.replace(f"t.me/{old_tag[1:]}", f"t.me/{new_username}")
                                break
                    
                    if replaced_url:
                        msg_data["webpage_url_replaced"] = replaced_url
                        logger.info(f"Replaced webpage URL: {webpage.url} → {replaced_url}")
                
                # Some webpages have embedded photos/images
                if hasattr(webpage, 'photo') and webpage.photo:
                    logger.info("Webpage has embedded photo, but we're handling this as a text message")
                
                # Flag if this is a rich preview that needs special handling
                msg_data["has_webpage_content"] = has_webpage_content
                
                # Return early to prevent further processing as media
                return msg_data
            
            else:
                # Generic media type
                media_type = "unknown"
        
        except Exception as e:
            logger.error(f"Error determining media type: {str(e)}")
            media_type = "unknown"
        
        try:
            # Generate appropriate file extension
            extension = ".bin"  # Default
            
            if is_photo:
                extension = ".jpg"
            elif is_video:
                extension = ".mp4"
            elif is_gif:
                extension = ".mp4"
            elif is_voice:
                extension = ".ogg"
            elif is_audio:
                extension = ".mp3"
            elif is_sticker:
                extension = ".webp"
            
            # If we have a document with a filename, try to extract extension
            if hasattr(message.media, 'document') and getattr(message.media.document, 'mime_type', None):
                file_name = None
                
                # Try to get the original filename
                for attr in message.media.document.attributes:
                    if hasattr(attr, 'file_name') and attr.file_name:
                        file_name = attr.file_name
                        break
                
                # Get extension from filename
                if file_name and '.' in file_name:
                    extension = f'.{file_name.split(".")[-1]}'
            
            # Download the media - use a more efficient method with proper chunk size
            # Create a unique temp directory to prevent file conflicts
            temp_dir = tempfile.mkdtemp(prefix="tg_media_")
            file_path = os.path.join(temp_dir, f"media{extension}")
            
            # Log that we're attempting to download the media
            logger.info(f"Downloading media to {file_path}")
            
            # Use a more efficient download with larger chunks for faster performance
            # Use simplified download options to avoid parameter compatibility issues
            download_options = {
                'file': file_path
                # Removed problematic parameters causing 'dc_id' error
            }
            
            # Download the media
            downloaded_path = await message.download_media(**download_options)
            
            if downloaded_path:
                logger.info(f"Successfully downloaded media to {downloaded_path}")
                file_path = downloaded_path
                
                # Store media info
                msg_data["media_data"] = {
                    "type": media_type,
                    "mime_type": getattr(message.media.document, 'mime_type', None) if hasattr(message.media, 'document') else None,
                    "file_name": file_name if 'file_name' in locals() else None,
                    "caption": msg_data["text"],
                    "is_photo": is_photo,
                    "is_video": is_video,
                    "is_gif": is_gif,
                    "is_sticker": is_sticker,
                    "is_voice": is_voice,
                    "is_audio": is_audio,
                    "is_document": is_document
                }
                
                msg_data["file_path"] = file_path
                msg_data["text"] = None  # Text will be used as caption instead
            else:
                logger.error("Failed to download media")
                raise Exception("Failed to download media file")
        
        except Exception as e:
            logger.error(f"Error downloading media: {str(e)}")
            # Continue without media if there's an error
    
    return msg_data

# Ultra minimal message mapping storage - extremely limited to only 3 recent messages
# Format: {(source_channel_id, source_message_id): {dest_channel: dest_msg_id}}
message_mapping = {}

# Extremely limited storage to enable edit synchronization but minimize memory usage
MAX_RECENT_MESSAGES = 3  # Store only the 3 most recent messages

# List to track the order of message mappings (for cleaning up oldest entries)
message_mapping_order = []

# Function to add a message mapping to the recent messages cache (limited to 3 messages max)
async def add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id):
    """Add a message mapping with extremely limited storage (3 messages max)
    
    This function stores only the absolute minimum needed for edit synchronization
    while keeping an extremely small memory footprint
    """
    key = (source_channel_id, source_message_id)
    
    # Check if mapping exists
    if key not in message_mapping:
        message_mapping[key] = {}
        # Add to order tracking
        message_mapping_order.append(key)
        
        # If we've exceeded the very strict limit, remove oldest entries
        while len(message_mapping_order) > MAX_RECENT_MESSAGES:
            oldest_key = message_mapping_order.pop(0)  # Remove oldest entry
            message_mapping.pop(oldest_key, None)
    
    # Add the mapping
    message_mapping[key][dest_channel] = dest_msg_id

# Event handler for new messages in source channels
async def handle_new_message(event):
    """Handle new messages in source channels"""
    logger.info(f"=== NEW MESSAGE EVENT RECEIVED ===\nFrom channel: {event.chat_id}\nMessage ID: {event.message.id if hasattr(event, 'message') else 'Unknown'}")
    logger.info(f"Active channels: Source={active_channels['source']}, Destination={active_channels['destinations']}")
    logger.info(f"Reposting active: {reposting_active}")
    await process_message_event(event, is_edit=False)

# Event handler for edited messages in source channels
async def handle_edited_message(event):
    """Handle edited messages in source channels"""
    await process_message_event(event, is_edit=True)
    
# Event handler for deleted messages in source channels
async def handle_deleted_message(event):
    """Handle deleted messages in source channels and sync deletion to destination channels if enabled"""
    global sync_deletions
    
    # Check if deletion synchronization is enabled
    if not sync_deletions:
        logger.info("Message deletion detected, but deletion sync is disabled")
        return
        
    # Log the deletion event
    logger.info(f"Message deletion detected in channel {event.chat_id}")
    
    try:
        # Get the deleted message IDs
        deleted_ids = event.deleted_ids
        source_channel_id = event.chat_id
        
        # Process each deleted message
        for deleted_id in deleted_ids:
            logger.info(f"Processing deletion of message {deleted_id} from channel {source_channel_id}")
            
            # Look for this message in our limited mapping cache
            key = (source_channel_id, deleted_id)
            if key in message_mapping:
                # We found a mapping for this message
                logger.info(f"Found mapping for deleted message {deleted_id}")
                
                # For each destination where we previously sent this message
                for dest_channel, dest_msg_id in message_mapping[key].items():
                    try:
                        # Delete the message from destination channel
                        logger.info(f"Deleting message {dest_msg_id} from destination channel {dest_channel}")
                        await user_client.delete_messages(dest_channel, dest_msg_id)
                        logger.info(f"Successfully deleted message {dest_msg_id} from channel {dest_channel}")
                    except Exception as e:
                        logger.error(f"Error deleting message {dest_msg_id} from channel {dest_channel}: {e}")
                
                # Remove the mapping since it's no longer needed
                message_mapping.pop(key, None)
                if key in message_mapping_order:
                    message_mapping_order.remove(key)
                logger.info(f"Removed mapping for deleted message {deleted_id}")
            else:
                logger.info(f"No mapping found for deleted message {deleted_id} (only store last {MAX_RECENT_MESSAGES})")
    except Exception as e:
        logger.error(f"Error processing message deletion event: {e}")
    
async def process_message_event(event, is_edit=False):
    """Process message events (new or edited)"""
    # Check if reposting is active
    global reposting_active
    
    # Get source channel and message ID
    source_channel_id = None
    source_message_id = None
    
    try:
        source_channel_id = event.chat_id
        source_message_id = event.message.id
    except:
        if is_edit:
            logger.info("Edited message received (couldn't get chat_id or message_id)")
        else:
            logger.info("New message received (couldn't get chat_id or message_id)")
    
    # Log the event
    if is_edit:
        logger.info(f"Edited message received in channel {source_channel_id}, message ID: {source_message_id}")
    else:
        logger.info(f"New message received in channel {source_channel_id}")
        
    # Check reposting state
    if not reposting_active:
        logger.info("Reposting is not active, ignoring message")
        return
    
    # Initialize sent_destinations dictionary at the top level
    sent_destinations = {}
    
    try:
        # Get the message
        message = event.message
        
        # For edited messages, check if we have a mapping to update existing messages
        if is_edit and source_channel_id and source_message_id:
            logger.info(f"Edited message received from channel {source_channel_id}, message ID: {source_message_id}")
            
            # Check if we have this message in our limited mapping cache
            key = (source_channel_id, source_message_id)
            if key in message_mapping:
                logger.info(f"Found mapping for edited message - will update in destination channels")
                
                # For each destination where we previously sent this message
                for dest_channel, dest_msg_id in message_mapping[key].items():
                    logger.info(f"Will update message in channel {dest_channel}, message ID: {dest_msg_id}")
                    
                    try:
                        # Process message for reposting
                        msg_data = await process_message_for_reposting(message)
                        
                        # Update the message in the destination channel
                        if msg_data["has_media"]:
                            # For media messages, we can't edit directly
                            # We'll need to delete and repost
                            logger.info(f"Can't directly edit media message. Will delete and repost.")
                            
                            try:
                                # Try to delete the old message
                                await user_client.delete_messages(dest_channel, dest_msg_id)
                                logger.info(f"Deleted old message {dest_msg_id} in channel {dest_channel}")
                            except Exception as e:
                                logger.error(f"Error deleting message {dest_msg_id} in channel {dest_channel}: {e}")
                                
                            # Let the regular flow repost the message
                            # We'll continue below with the normal posting mechanism
                        else:
                            # For text messages, we can edit directly
                            logger.info(f"Updating text message {dest_msg_id} in channel {dest_channel}")
                            
                            try:
                                await user_client.edit_message(
                                    dest_channel,
                                    dest_msg_id,
                                    msg_data["text"],
                                    parse_mode='html',
                                    link_preview=msg_data.get("link_preview", True)
                                )
                                logger.info(f"Successfully updated message {dest_msg_id} in channel {dest_channel}")
                                
                                # Flag this destination as already handled
                                sent_destinations[dest_channel] = dest_msg_id
                            except Exception as e:
                                logger.error(f"Error updating message {dest_msg_id} in channel {dest_channel}: {e}")
                                # Let the regular flow repost the message
                                # We'll continue below with the normal posting mechanism
                    except Exception as e:
                        logger.error(f"Error processing edited message: {e}")
                
                # Return if we've handled all destinations
                if len(sent_destinations) == len(active_channels["destinations"] or [active_channels["destination"]]):
                    logger.info("All destinations updated successfully, no need to repost")
                    return
                
                logger.info("Some destinations couldn't be updated, will repost to remaining destinations")
            else:
                logger.info(f"No mapping found for edited message (only store last {MAX_RECENT_MESSAGES})")
                logger.info(f"Will be posted as a new message instead")
        
        # Process message for reposting (apply tag replacements) - if not already done above
        if 'msg_data' not in locals():
            msg_data = await process_message_for_reposting(message)
        
        # Apply content filtering if enabled
        if content_filters["enabled"]:
            should_repost = await filter_content(msg_data)
            if not should_repost:
                logger.info("Message filtered out based on content filters")
                return
                
        # Determine destination channels
        destinations = active_channels["destinations"]
        if not destinations:
            # Fallback to single destination if no multiple destinations set
            if active_channels["destination"]:
                destinations = [active_channels["destination"]]
            else:
                logger.error("No destination channels configured.")
                return
                
        logger.info(f"Preparing to send message to {len(destinations)} destination channels")
        
        # The actual send operation depends on the message type
        if msg_data["has_media"]:
            # Handle media messages
            # Process caption for hyperlinks if applicable
            caption_html = None
            
            if msg_data["media_data"]["caption"] and '[' in msg_data["media_data"]["caption"] and '](' in msg_data["media_data"]["caption"]:
                # Caption processing code for hyperlinks
                logger.info("Caption may contain hyperlinks, processing...")
                
                # First look for markdown links [text](url) and convert to entities
                processed_text, markdown_entities = await detect_markdown_links(msg_data["media_data"]["caption"])
                
                if markdown_entities:
                    logger.info(f"Found {len(markdown_entities)} hyperlinks in caption")
                    
                    # Process these hyperlinks (replace t.me links)
                    modified_text, processed_entities = await find_replace_channel_tags(processed_text, [
                        MessageEntityTextUrl(
                            offset=e['offset'],
                            length=e['length'],
                            url=e['url']
                        ) for e in markdown_entities
                    ])
                    
                    # Create HTML version of caption
                    parts = []
                    last_end = 0
                    
                    # Sort entities by offset
                    sorted_entities = sorted(processed_entities, key=lambda e: e['offset'])
                    
                    # Process each entity
                    for entity_dict in sorted_entities:
                        if entity_dict['type'] == 'MessageEntityTextUrl':
                            # Add any text before this entity
                            start = entity_dict['offset']
                            end = start + entity_dict['length']
                            if start > last_end:
                                parts.append(modified_text[last_end:start])
                            
                            # Add the entity as an HTML tag
                            link_text = modified_text[start:end]
                            parts.append(f'<a href="{entity_dict["url"]}">{link_text}</a>')
                            
                            # Update the last end position
                            last_end = end
                    
                    # Add any remaining text
                    if last_end < len(modified_text):
                        parts.append(modified_text[last_end:])
                    
                    # Build the final HTML caption
                    caption_html = ''.join(parts)
                    logger.info(f"Formatted HTML caption: {caption_html}")

            # Send the media with appropriate formatting
            logger.info(f"Sending media of type: {msg_data['media_data']['type']}")
            
            # Send to each destination channel
            for dest_channel in destinations:
                try:
                    logger.info(f"Sending to destination channel: {dest_channel}")
                    file_attributes = []
                    
                    # Add attributes from original message if available
                    if "document_attributes" in msg_data:
                        file_attributes = msg_data["document_attributes"]
                    
                    # Variable to store the sent message for mapping
                    dest_message = None
                    
                    # Common upload parameters for optimization
                    upload_options = {
                        'caption': caption_html if caption_html else msg_data["media_data"]["caption"],
                        'parse_mode': 'html',
                        'force_document': False,
                        'attributes': file_attributes,
                        'part_size_kb': 1024,  # Use 1MB chunks for upload too
                        'workers': 4           # Use multiple workers for faster upload
                    }
                    
                    # Handle each media type specifically
                    if msg_data["media_data"]["is_photo"]:
                        # Photos
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            **upload_options
                        )
                        logger.info(f"Sent as photo to {dest_channel}")
                        
                    elif msg_data["media_data"]["is_video"]:
                        # Videos
                        upload_options['video'] = True  # Explicitly mark as video
                        upload_options['supports_streaming'] = True  # Better for streaming
                        
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            **upload_options
                        )
                        logger.info(f"Sent as video to {dest_channel}")
                    
                    elif msg_data["media_data"]["is_gif"]:
                        # GIFs
                        upload_options['video'] = True  # GIFs are sent as videos
                        upload_options['supports_streaming'] = True  # Better for GIF-like videos
                        
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            **upload_options
                        )
                        logger.info(f"Sent as gif to {dest_channel}")
                    
                    elif msg_data["media_data"]["is_sticker"]:
                        # Stickers
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as sticker to {dest_channel}")
                    
                    elif msg_data["media_data"]["is_voice"]:
                        # Voice messages
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            voice=True,  # Explicitly mark as voice
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as voice message to {dest_channel}")
                    
                    elif msg_data["media_data"]["is_audio"]:
                        # Audio files
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            attributes=file_attributes,
                            audio=True  # Explicitly mark as audio
                        )
                        logger.info(f"Sent as audio to {dest_channel}")
                    
                    elif msg_data["media_data"]["is_document"]:
                        # Documents/files
                        file_name = msg_data["media_data"].get("file_name", None)
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=True,  # Send as document
                            attributes=file_attributes,
                            file_name=file_name if file_name else None
                        )
                        logger.info(f"Sent as document to {dest_channel}")
                    
                    else:
                        # Unknown type - let Telegram determine how to send it
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,  # Let Telegram decide
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as unknown media type to {dest_channel}")
                    
                    # No message mapping is stored (per user requirements)
                    # Simply track successful delivery for logging purposes
                    if not is_edit and source_channel_id and source_message_id and dest_message:
                        dest_msg_id = dest_message.id
                        sent_destinations[dest_channel] = dest_msg_id
                        logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")
                        
                except Exception as e:
                    logger.error(f"Error sending media to {dest_channel}: {str(e)}")
                    
                    # Fallback - try sending without special attributes
                    try:
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=msg_data["media_data"]["caption"],
                            force_document=False  # Let Telegram determine type
                        )
                        logger.info(f"Sent media using fallback method to {dest_channel}")
                        
                        # No message mapping stored (per user requirements)
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")
                    except Exception as e2:
                        logger.error(f"Error in fallback send to {dest_channel}: {str(e2)}")
                        
                        # Last resort - try as document
                        try:
                            dest_message = await user_client.send_file(
                                dest_channel,
                                msg_data["file_path"],
                                caption=msg_data["media_data"]["caption"],
                                force_document=True
                            )
                            logger.info(f"Sent as document after all other methods failed to {dest_channel}")
                            
                            # Store mapping even for last resort method
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                                sent_destinations[dest_channel] = dest_msg_id
                        except Exception as e3:
                            logger.error(f"Complete failure sending media to {dest_channel}: {str(e3)}")
            
            # Clean up the temporary file
            if msg_data["file_path"] and os.path.exists(msg_data["file_path"]):
                os.unlink(msg_data["file_path"])
        
        else:  # Text-only messages
            # Track which destinations received the message
            sent_destinations = {}
            
            # For messages with hyperlinks, try a different approach
            if msg_data.get("html_backup", False):
                # Send to each destination channel
                for dest_channel in destinations:
                    try:
                        logger.info(f"Sending text message with hyperlinks to {dest_channel}")
                        
                        # Create formatted HTML with hyperlinks
                        html_message = msg_data["text"]
                        
                        # We'll create a completely new HTML document from scratch to fix duplication issues
                        
                        # Get the raw text
                        raw_text = msg_data["text"]
                        
                        # Create parts of the message
                        parts = []
                        last_end = 0
                        
                        # Sort entities by offset
                        sorted_entities = sorted(msg_data["entities"], key=lambda e: e.offset)
                        
                        # Track which portions of the text have already been processed to avoid duplication
                        processed_ranges = []
                        
                        # First, consolidate overlapping entities to prevent doubling
                        consolidated_entities = []
                        for entity in sorted_entities:
                            if isinstance(entity, MessageEntityTextUrl):
                                # Check if this range overlaps with any processed range
                                entity_range = (entity.offset, entity.offset + entity.length)
                                if not any(start <= entity_range[0] < end for start, end in processed_ranges):
                                    consolidated_entities.append(entity)
                                    processed_ranges.append(entity_range)
                        
                        # Now we have a clean list of non-overlapping entities
                        # Process each entity one by one
                        last_end = 0
                        for entity in consolidated_entities:
                            if isinstance(entity, MessageEntityTextUrl):
                                # Add any text before this entity
                                if entity.offset > last_end:
                                    parts.append(raw_text[last_end:entity.offset])
                                
                                # Add the entity as an HTML tag
                                link_text = raw_text[entity.offset:entity.offset + entity.length]
                                
                                # Clean the link text if it contains markdown formatting
                                if '[' in link_text and '](' in link_text:
                                    # Try to extract just the text part
                                    md_match = re.search(r'\[([^\]]+)\]', link_text)
                                    if md_match:
                                        link_text = md_match.group(1)
                                        logger.info(f"Cleaned link text from markdown: '{link_text}'")
                                
                                # Enhanced fix for duplication issue ("MeMe") - check if the text appears to be duplicated
                                # by comparing first and second half
                                if len(link_text) > 1 and len(link_text) % 2 == 0:
                                    half_len = len(link_text) // 2
                                    first_half = link_text[:half_len]
                                    second_half = link_text[half_len:]
                                    if first_half == second_half:
                                        logger.info(f"Detected duplicated text '{link_text}', using only '{first_half}'")
                                        link_text = first_half
                                
                                parts.append(f'<a href="{entity.url}">{link_text}</a>')
                                
                                # Update the last end position
                                last_end = entity.offset + entity.length
                        
                        # Add any remaining text
                        if last_end < len(raw_text):
                            parts.append(raw_text[last_end:])
                        
                        # Build the final HTML message
                        html_message = ''.join(parts)
                        
                        # Send the HTML formatted message
                        dest_message = await user_client.send_message(
                            dest_channel,
                            html_message,
                            parse_mode='html'
                        )
                        logger.info(f"Successfully sent HTML message to {dest_channel}")
                        
                        # No message mapping stored (per user requirements)
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")
                            
                    except Exception as e:
                        logger.error(f"Error sending HTML message to {dest_channel}: {str(e)}")
                        
                        # Try alternate HTML approach
                        try:
                            # Try alternate method with markdown links
                            markdown_text = msg_data["text"]
                            markdown_replacements = []
                            
                            # Process entities for markdown replacements
                            for entity in msg_data["entities"]:
                                if isinstance(entity, MessageEntityTextUrl):
                                    link_text = markdown_text[entity.offset:entity.offset + entity.length]
                                    markdown_replacements.append({
                                        'start': entity.offset,
                                        'end': entity.offset + entity.length,
                                        'text': link_text,
                                        'url': entity.url
                                    })
                            
                            # Sort from end to start to avoid offset issues
                            markdown_replacements.sort(key=lambda x: x['start'], reverse=True)
                            
                            # Apply the replacements
                            for replacement in markdown_replacements:
                                start = replacement['start']
                                end = replacement['end']
                                link_text = replacement['text']
                                markdown_link = f'<a href="{replacement["url"]}">{link_text}</a>'
                                markdown_text = markdown_text[:start] + markdown_link + markdown_text[end:]
                            
                            # Send with alternate format
                            dest_message = await user_client.send_message(
                                dest_channel,
                                markdown_text,
                                parse_mode='html'
                            )
                            logger.info(f"Successfully sent alternate HTML message to {dest_channel}")
                            
                            # No message mapping stored (per user requirements)
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                sent_destinations[dest_channel] = dest_msg_id
                                logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")
                        except Exception as e2:
                            logger.error(f"Error sending alternate HTML message to {dest_channel}: {str(e2)}")
            
            else:  # Regular text messages without hyperlinks
                # Send to each destination channel
                for dest_channel in destinations:
                    try:
                        # First try with entities if available
                        if msg_data["entities"]:
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"],
                                formatting_entities=msg_data["entities"]  # Use formatting_entities instead of entities
                            )
                            logger.info(f"Sent message with entities to {dest_channel}")
                        else:
                            # If no entities, use parse_mode
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"],
                                parse_mode='html'
                            )
                            logger.info(f"Sent message with HTML parse mode to {dest_channel}")
                            
                        # No message mapping stored (per user requirements)
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")
                            
                    except Exception as e:
                        logger.error(f"Error sending message to {dest_channel}: {str(e)}")
                        # Fallback to sending plain text
                        try:
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"]
                            )
                            logger.info(f"Sent plain text message to {dest_channel}")
                            
                            # Store the message mapping
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                # Use memory-efficient mapping function
                                await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                                sent_destinations[dest_channel] = dest_msg_id
                        except Exception as e2:
                            logger.error(f"Failed to send message to {dest_channel}: {str(e2)}")
        
        # Log the message mapping status
        logger.info(f"Successfully sent message to {len(sent_destinations)} destination channels")
        
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler with session information"""
    # Get the message that triggered this command
    trigger_message = update.message
    if trigger_message:
        # Try to delete the message that called the /start command
        try:
            await trigger_message.delete()
            logger.info(f"Deleted /start command message from user {trigger_message.from_user.id}")
        except Exception as e:
            logger.error(f"Failed to delete /start command message: {str(e)}")
            # Continue even if deletion fails
            
    # Clear any existing messages for this user
    user_id = update.effective_user.id
    if user_id in user_message_history:
        # Clear existing messages
        for chat_id, msg_ids in user_message_history[user_id].items():
            for msg_id in msg_ids:
                try:
                    await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    logger.info(f"Deleted old message {msg_id} in chat {chat_id} for user {user_id}")
                except Exception as e:
                    logger.warning(f"Failed to delete message {msg_id} in chat {chat_id}: {str(e)}")
        # Reset the tracking for this user        
        user_message_history[user_id] = {}
    
    # Check if this is admin by default
    if user_id == 7325746010:
        # Ensure this admin is in the ADMIN_USERS list
        if user_id not in ADMIN_USERS:
            ADMIN_USERS.append(user_id)
            await save_admin_config()
            
    if user_id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this bot.🥹")
        return
    
    # Check if API credentials and session are available
    missing_credentials = False
    if not API_ID or not API_HASH or not USER_SESSION:
        missing_credentials = True
    
    # Group buttons by functionality for better organization
    
    # Channel configuration section
    channel_buttons = [
        [
            InlineKeyboardButton("➕ Add Source", callback_data="add_source"),
            InlineKeyboardButton("➖ Remove Source", callback_data="remove_source")
        ],
        [InlineKeyboardButton("🎯 Set Destination Channel", callback_data="set_destination")],
        [InlineKeyboardButton("📨 Manage Destinations", callback_data="manage_destinations")],
        [InlineKeyboardButton("⚙️ Channel Management", callback_data="channel_settings_menu")]
    ]
    
    # Controls section - operation buttons
    control_buttons = [
        [
            InlineKeyboardButton("▶️ Start Reposting", callback_data="start_reposting"),
            InlineKeyboardButton("⏹️ Stop Reposting", callback_data="stop_reposting")
        ]
    ]
    
    # Settings section
    settings_buttons = [
        [InlineKeyboardButton("🏷️ Manage Tags", callback_data="manage_tags")],
        [InlineKeyboardButton("🚩 Content Filters", callback_data="content_filters")],
        [InlineKeyboardButton("👥 Manage Admins", callback_data="manage_admins")],
        [InlineKeyboardButton("ℹ️ View Config", callback_data="view_config")],
        [InlineKeyboardButton("🧹 Toggle Clean Mode", callback_data="toggle_clean_mode")],
        [InlineKeyboardButton("🗑️ Deletion Sync Settings", callback_data="deletion_sync")]
    ]
    
    # Add API credentials section if missing
    if missing_credentials:
        settings_buttons.insert(0, [InlineKeyboardButton("🔑 Configure API Credentials", callback_data="config_api")])
    
    # Information section
    info_buttons = [
        [InlineKeyboardButton("📊 Session Info", callback_data="session_info")]
    ]
    
    # Combine all sections into the keyboard
    keyboard = []
    keyboard.extend(channel_buttons)
    keyboard.extend(control_buttons)
    keyboard.extend(settings_buttons)
    keyboard.extend(info_buttons)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = "Welcome to the Channel Reposter Bot!\n\n" \
    "This bot reposts content from source channels to a destination channel " \
    "without the forward tag, and can replace channel tags with custom values.\n\n"
    
    if missing_credentials:
        welcome_text += "⚠️ API credentials are missing. You need to configure them to use full reposting functionality.\n\n"
    
    welcome_text += "Use the buttons below to configure and control the bot."
    
    # Delete previous menu messages if they exist in global tracking
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    start_message_id = update.message.message_id
    
    # Check if this is the first time the user has used /start by checking user_data
    send_mkush = False
    
    # Only send the ªMkUsH message if this is actually the first-ever startup for this user
    if "first_start_done" not in context.user_data:
        # Mark that we've now processed the first start
        context.user_data["first_start_done"] = True
        # Set flag to send the special message
        send_mkush = True
        logger.info(f"First-time startup detected for user {user_id}, will send ªMkUsH message")
    
    # Only for first-time startup: send a special "ªMkUsH" message that:
    # 1. Will appear only ONCE during the very first startup for each user
    # 2. Will stay at the top permanently (never deleted)
    # 3. Helps prevent Telegram's blue start button from being too prominent
    if send_mkush:
        try:
            # This special message stays permanently at the top
            permanent_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="ªMkUsH"  # The exact text with correct capitalization as requested
            )
            # Store this message ID to ensure we never delete it during cleanup
            context.user_data["mkush_message_id"] = permanent_msg.message_id
            logger.info(f"First startup: Sent permanent ªMkUsH message with ID: {permanent_msg.message_id}")
        except Exception as e:
            logger.error(f"Failed to send permanent message: {str(e)}")

    # Important: The ªMkUsH message now only appears at first startup and stays at the top permanently
    
    # Forcefully delete the /start command to maintain clean interface
    try:
        # Delete the original command message
        await context.bot.delete_message(chat_id=chat_id, message_id=start_message_id)
        logger.info(f"Deleted original /start command message")
    except Exception as e:
        logger.error(f"Failed to delete start message: {str(e)}")
    
    # Check both global tracking and user_data context
    message_ids = []
    
    # Check global tracking first
    if user_id in user_message_history and chat_id in user_message_history[user_id]:
        logger.info(f"Found {len(user_message_history[user_id][chat_id])} messages in global tracking")
        message_ids.extend(user_message_history[user_id][chat_id])
    
    # Also check context for backward compatibility
    if "message_ids" in context.user_data:
        logger.info(f"Found {len(context.user_data['message_ids'])} messages in user_data")
        message_ids.extend(context.user_data["message_ids"])
    
    # Delete all stored messages except the permanent ªMkUsH message
    mkush_message_id = context.user_data.get("mkush_message_id", None)
    
    for msg_id in message_ids:
        # Skip deletion of the permanent ªMkUsH message
        if mkush_message_id and msg_id == mkush_message_id:
            logger.info(f"Skipping deletion of permanent ªMkUsH message: {msg_id}")
            continue
            
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            logger.info(f"Deleted stored message {msg_id}")
        except Exception as e:
            logger.error(f"Error deleting stored message {msg_id}: {str(e)}")
    
    # Initialize or reset the message tracking
    context.user_data["message_ids"] = []
    
    # Initialize the user's entry in the global tracking if needed
    if user_id not in user_message_history:
        user_message_history[user_id] = {}
    
    # Clear the existing messages for this chat
    user_message_history[user_id][chat_id] = []
    
    # First send the image without buttons and store its message ID
    try:
        img_message = await update.message.reply_photo(
            photo=open("assets/menu_image.jpeg", "rb"),
            caption="Channel Reposter Bot"
        )
        # Store in context for backward compatibility
        context.user_data["message_ids"].append(img_message.message_id)
        # Store in global tracking
        user_message_history[user_id][chat_id].append(img_message.message_id)
    except Exception as e:
        logger.error(f"Error sending image: {str(e)}")
    
    # Then send a separate message with the menu text and buttons and store its message ID
    menu_message = await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup
    )
    # Store in context for backward compatibility
    context.user_data["message_ids"].append(menu_message.message_id)
    # Store in global tracking
    user_message_history[user_id][chat_id].append(menu_message.message_id)

async def edit_message_smartly(message, text, reply_markup=None, parse_mode=None):
    """Smartly edit a message based on its type (photo or text)"""
    is_photo = hasattr(message, 'photo') and message.photo
    
    try:
        if is_photo:
            # For photos, edit the caption
            return await message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            # For text messages, edit the text
            return await message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
    except Exception as e:
        logger.error(f"Error editing message: {str(e)}")
        # Fallback - send a new message
        return await message.reply_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks including session info"""
    global reposting_active, sync_deletions
    
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    # Allow the user to continue if they're adding themselves as admin or configuring API
    if (query.data != "manage_admins" and 
        query.data != "add_admin" and 
        query.data != "config_api" and 
        not query.data.startswith("confirm_add_admin_") and
        not query.data.startswith("set_") and 
        user_id not in ADMIN_USERS):
        try:
            # Use our smart edit function instead of edit_message_text directly
            await edit_message_smartly(query.message, "You are not authorized to use this bot.🥹")
        except Exception as e:
            logger.error(f"Error in auth check: {str(e)}")
        return
    
    if query.data == "add_source":
        text = "📥 Add Source Channel\n\n" \
               "Please send the channel identifier in any of these formats:\n\n" \
               "✅ Numeric ID: `-1001234567890`\n" \
               "✅ Username: `@channelname`\n" \
               "✅ Link: `https://t.me/channelname`\n\n" \
               "💡 Tip: Numeric IDs are the most reliable. You can get a channel's numeric ID " \
               "by forwarding any message from the channel to @userinfobot.\n\n" \
               "⚠️ Important: You must be a member of the source channel to receive its messages."
               
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="back_to_menu")]])
        
        # Use our helper function to smartly edit the message
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=buttons,
            parse_mode="HTML"
        )
        
        context.user_data["awaiting"] = "source_channel"
    
    elif query.data == "remove_source":
        if not active_channels["source"]:
            await query.edit_message_text(
                "No source channels configured yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
            return
        
        keyboard = []
        for channel in active_channels["source"]:
            # Get channel info
            info = await get_entity_info(user_client, channel)
            display_name = info.get("title", str(channel)) if info else str(channel)
            keyboard.append([InlineKeyboardButton(f"🗑️ Remove: {display_name}", callback_data=f"remove_{channel}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")])
        await query.edit_message_text(
            "📋 Select a source channel to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("remove_"):
        try:
            channel_id = int(query.data.split("_")[1])
            if channel_id in active_channels["source"]:
                active_channels["source"].remove(channel_id)
                await save_config()
                await query.edit_message_text(
                    f"✅ Removed channel {channel_id} from sources.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
            else:
                await query.edit_message_text(
                    "❌ Channel not found in sources.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
        except ValueError:
            # Handle non-integer values in the callback data
            logger.warning(f"Invalid channel ID format in callback: {query.data}")
            await query.edit_message_text(
                "❌ Invalid channel ID format.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
    
    elif query.data == "manage_destinations":
        # Menu for managing multiple destination channels
        keyboard = [
            [InlineKeyboardButton("➕ Add Destination", callback_data="add_destination")]
        ]
        
        # Only show remove button if there are destinations to remove
        if active_channels["destinations"]:
            keyboard.append([InlineKeyboardButton("➖ Remove Destination", callback_data="remove_destination")])
            
            # Show current destinations
            text = "📋 Current Destination Channels:\n\n"
            for idx, dest in enumerate(active_channels["destinations"], 1):
                # Get channel info
                info = await get_entity_info(user_client, dest)
                display_name = info.get("title", str(dest)) if info else str(dest)
                text += f"{idx}. {display_name}\n"
        else:
            text = "📋 No destination channels configured yet.\n\nAdd a destination channel to start reposting."
        
        keyboard.append([InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "add_destination":
        text = "📨 Add Destination Channel\n\n" \
               "Please send the channel identifier in any of these formats:\n\n" \
               "✅ Numeric ID: `-1001234567890`\n" \
               "✅ Username: `@channelname`\n" \
               "✅ Link: `https://t.me/channelname`\n\n" \
               "💡 Tip: Numeric IDs are the most reliable. You can get a channel's numeric ID " \
               "by forwarding any message from the channel to @userinfobot.\n\n" \
               "⚠️ Important: The bot must be an admin with 'Post Messages' permission in the destination channel."
        
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="manage_destinations")]])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=buttons,
            parse_mode="HTML"
        )
        
        context.user_data["awaiting"] = "destination_channel_add"

    elif query.data == "remove_destination":
        if not active_channels["destinations"]:
            await edit_message_smartly(
                query.message,
                "No destination channels configured yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
            )
            return
        
        keyboard = []
        for channel in active_channels["destinations"]:
            # Get channel info
            info = await get_entity_info(user_client, channel)
            display_name = info.get("title", str(channel)) if info else str(channel)
            keyboard.append([InlineKeyboardButton(f"🗑️ Remove: {display_name}", callback_data=f"remove_dest_{channel}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")])
        await edit_message_smartly(
            query.message,
            "📋 Select a destination channel to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("remove_dest_"):
        try:
            channel_id = int(query.data.split("_")[-1])
            if channel_id in active_channels["destinations"]:
                active_channels["destinations"].remove(channel_id)
                # If this was the last/only destination, also clear legacy destination
                if not active_channels["destinations"] and active_channels["destination"] == channel_id:
                    active_channels["destination"] = None
                await save_config()
                await edit_message_smartly(
                    query.message,
                    f"✅ Removed channel from destinations.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                )
            else:
                await edit_message_smartly(
                    query.message,
                    "❌ Channel not found in destinations.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                )
        except ValueError:
            # Handle non-integer values in the callback data
            logger.warning(f"Invalid channel ID format in callback: {query.data}")
            await edit_message_smartly(
                query.message,
                "❌ Invalid channel ID format.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
            )
        
    elif query.data == "content_filters":
        # Content filtering menu
        filter_status = "Enabled" if content_filters["enabled"] else "Disabled"
        
        text = f"🚩 Content Filters: {filter_status}\n\n"
        
        # Show current filter settings if enabled
        if content_filters["enabled"]:
            # Show keyword filters
            text += "📝 Keyword Filters:\n"
            if content_filters["keywords"]["include"]:
                text += "✅ Include (must contain at least one):\n"
                for kw in content_filters["keywords"]["include"]:
                    text += f"   • {kw}\n"
            if content_filters["keywords"]["exclude"]:
                text += "❌ Exclude (must not contain any):\n"
                for kw in content_filters["keywords"]["exclude"]:
                    text += f"   • {kw}\n"
            if not content_filters["keywords"]["include"] and not content_filters["keywords"]["exclude"]:
                text += "   No keyword filters set\n"
                
            # Show media type filters
            text += "\n🖼️ Media Type Filters:\n"
            if content_filters["media_types"]["include"]:
                text += "✅ Include only these types:\n"
                for media_type in content_filters["media_types"]["include"]:
                    text += f"   • {media_type}\n"
            if content_filters["media_types"]["exclude"]:
                text += "❌ Exclude these types:\n"
                for media_type in content_filters["media_types"]["exclude"]:
                    text += f"   • {media_type}\n"
            if not content_filters["media_types"]["include"] and not content_filters["media_types"]["exclude"]:
                text += "   No media type filters set\n"
        else:
            text += "Content filtering is disabled. Enable it to filter messages based on keywords or media types.\n"
        
        # Create keyboard with filter options
        keyboard = [
            [InlineKeyboardButton(f"{'🔴 Disable' if content_filters['enabled'] else '🟢 Enable'} Filters", 
                               callback_data="toggle_content_filters")],
        ]
        
        # Only show these buttons if filtering is enabled
        if content_filters["enabled"]:
            keyboard.extend([
                [InlineKeyboardButton("📝 Keyword Filters", callback_data="keyword_filters")],
                [InlineKeyboardButton("🖼️ Media Type Filters", callback_data="media_filters")],
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif query.data == "toggle_content_filters":
        # Toggle content filtering on/off
        content_filters["enabled"] = not content_filters["enabled"]
        
        # Save to config
        BOT_CONFIG["content_filters_enabled"] = content_filters["enabled"]
        save_bot_config()
        
        status = "enabled" if content_filters["enabled"] else "disabled"
        await edit_message_smartly(
            query.message,
            f"Content filtering is now {status}.",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("◀️ Back to Filters", callback_data="content_filters")
            ]])
        )
        
    elif query.data == "keyword_filters":
        text = "📝 Keyword Filters\n\n" \
               "Keywords help you filter messages based on their text content.\n\n" \
               "✅ Include Keywords: Message must contain at least ONE of these keywords.\n" \
               "❌ Exclude Keywords: Message must NOT contain ANY of these keywords.\n\n" \
               "Current settings:\n"
        
        # Show current include keywords
        if content_filters["keywords"]["include"]:
            text += "\n✅ Include Keywords:\n"
            for idx, keyword in enumerate(content_filters["keywords"]["include"], 1):
                text += f"{idx}. {keyword}\n"
        else:
            text += "\n✅ Include Keywords: None (all messages pass this filter)\n"
            
        # Show current exclude keywords
        if content_filters["keywords"]["exclude"]:
            text += "\n❌ Exclude Keywords:\n"
            for idx, keyword in enumerate(content_filters["keywords"]["exclude"], 1):
                text += f"{idx}. {keyword}\n"
        else:
            text += "\n❌ Exclude Keywords: None (no messages are excluded by keyword)\n"
        
        # Create keyboard
        keyboard = [
            [InlineKeyboardButton("➕ Add Include Keyword", callback_data="add_include_keyword")],
            [InlineKeyboardButton("➕ Add Exclude Keyword", callback_data="add_exclude_keyword")],
        ]
        
        # Only show remove buttons if there are keywords to remove
        if content_filters["keywords"]["include"]:
            keyboard.append([InlineKeyboardButton("➖ Remove Include Keyword", callback_data="remove_include_keyword")])
        if content_filters["keywords"]["exclude"]:
            keyboard.append([InlineKeyboardButton("➖ Remove Exclude Keyword", callback_data="remove_exclude_keyword")])
            
        keyboard.append([InlineKeyboardButton("◀️ Back to Filters", callback_data="content_filters")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_include_keyword":
        await edit_message_smartly(
            query.message,
            "📝 Add Include Keyword\n\n"
            "Please send the keyword you want to add to the include list.\n\n"
            "Messages must contain at least ONE of your include keywords to be reposted.\n\n"
            "Keywords are not case-sensitive and can be partial words.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="keyword_filters")]])
        )
        context.user_data["awaiting"] = "add_include_keyword"
    
    elif query.data == "add_exclude_keyword":
        await edit_message_smartly(
            query.message,
            "📝 Add Exclude Keyword\n\n"
            "Please send the keyword you want to add to the exclude list.\n\n"
            "Messages containing ANY of your exclude keywords will NOT be reposted.\n\n"
            "Keywords are not case-sensitive and can be partial words.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="keyword_filters")]])
        )
        context.user_data["awaiting"] = "add_exclude_keyword"
    
    elif query.data == "remove_include_keyword":
        if not content_filters["keywords"]["include"]:
            await edit_message_smartly(
                query.message,
                "No include keywords to remove.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")]])
            )
            return
            
        # Create keyboard with buttons for each keyword
        keyboard = []
        for keyword in content_filters["keywords"]["include"]:
            keyboard.append([InlineKeyboardButton(f"Remove: {keyword}", callback_data=f"del_include_{keyword}")])  
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")])
        
        await edit_message_smartly(
            query.message,
            "Select an include keyword to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "remove_exclude_keyword":
        if not content_filters["keywords"]["exclude"]:
            await edit_message_smartly(
                query.message,
                "No exclude keywords to remove.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")]])
            )
            return
            
        # Create keyboard with buttons for each keyword
        keyboard = []
        for keyword in content_filters["keywords"]["exclude"]:
            keyboard.append([InlineKeyboardButton(f"Remove: {keyword}", callback_data=f"del_exclude_{keyword}")])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")])
        
        await edit_message_smartly(
            query.message,
            "Select an exclude keyword to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("del_include_"):
        # Extract the keyword from the callback data
        keyword = query.data[len("del_include_"):]
        
        if keyword in content_filters["keywords"]["include"]:
            content_filters["keywords"]["include"].remove(keyword)
            # Save the change to config
            BOT_CONFIG["filter_include_keywords"] = content_filters["keywords"]["include"]
            save_bot_config()
            await edit_message_smartly(
                query.message,
                f"Removed '{keyword}' from include keywords.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Keywords", callback_data="keyword_filters")]])
            )
        else:
            await edit_message_smartly(
                query.message,
                f"Keyword '{keyword}' not found in include list.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")]])
            )
    
    elif query.data.startswith("del_exclude_"):
        # Extract the keyword from the callback data
        keyword = query.data[len("del_exclude_"):]
        
        if keyword in content_filters["keywords"]["exclude"]:
            content_filters["keywords"]["exclude"].remove(keyword)
            # Save the change to config
            BOT_CONFIG["filter_exclude_keywords"] = content_filters["keywords"]["exclude"]
            save_bot_config()
            await edit_message_smartly(
                query.message,
                f"Removed '{keyword}' from exclude keywords.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Keywords", callback_data="keyword_filters")]])
            )
        else:
            await edit_message_smartly(
                query.message,
                f"Keyword '{keyword}' not found in exclude list.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="keyword_filters")]])
            )
        
    elif query.data == "media_filters":
        text = "🖼️ Media Type Filters\n\n" \
               "Media filters help you control which types of media are reposted.\n\n" \
               "✅ Include Types: ONLY these media types will be reposted.\n" \
               "❌ Exclude Types: These media types will NEVER be reposted.\n\n" \
               "If both lists are empty, all media types pass.\n\n" \
               "Current settings:\n"
               
        # Show current include media types
        if content_filters["media_types"]["include"]:
            text += "\n✅ Include Media Types:\n"
            for idx, media_type in enumerate(content_filters["media_types"]["include"], 1):
                text += f"{idx}. {media_type}\n"
        else:
            text += "\n✅ Include Media Types: None (all media types pass this filter)\n"
            
        # Show current exclude media types
        if content_filters["media_types"]["exclude"]:
            text += "\n❌ Exclude Media Types:\n"
            for idx, media_type in enumerate(content_filters["media_types"]["exclude"], 1):
                text += f"{idx}. {media_type}\n"
        else:
            text += "\n❌ Exclude Media Types: None (no media types are excluded)\n"
        
        # List available media types
        text += "\n📁 Available Media Types:\n"
        text += "photo, video, document, audio, voice, sticker, animation\n"
        
        # Create keyboard with toggle buttons for each media type
        # List of available media types
        available_media_types = ["photo", "video", "document", "audio", "voice", "sticker", "animation"]
        
        # Include media type toggle buttons
        include_keyboard = []
        include_row = []
        for i, media_type in enumerate(available_media_types):
            # Add checkmark if the type is in the include list
            status = "✅ " if media_type in content_filters["media_types"]["include"] else "◻️ "
            button = InlineKeyboardButton(f"{status}{media_type}", callback_data=f"toggle_include_media_{media_type}")
            
            # Create a new row every 2 buttons
            include_row.append(button)
            if len(include_row) == 2 or i == len(available_media_types) - 1:
                include_keyboard.append(include_row)
                include_row = []
        
        # Exclude media type toggle buttons
        exclude_keyboard = []
        exclude_row = []
        for i, media_type in enumerate(available_media_types):
            # Add checkmark if the type is in the exclude list
            status = "❌ " if media_type in content_filters["media_types"]["exclude"] else "◻️ "
            button = InlineKeyboardButton(f"{status}{media_type}", callback_data=f"toggle_exclude_media_{media_type}")
            
            # Create a new row every 2 buttons
            exclude_row.append(button)
            if len(exclude_row) == 2 or i == len(available_media_types) - 1:
                exclude_keyboard.append(exclude_row)
                exclude_row = []
        
        # Combine all sections
        keyboard = []
        keyboard.append([InlineKeyboardButton("✅ INCLUDE FILTERS (Toggle On/Off)", callback_data="none_action")])
        keyboard.extend(include_keyboard)
        
        # Add exclude section
        keyboard.append([InlineKeyboardButton("❌ EXCLUDE FILTERS (Toggle On/Off)", callback_data="none_action")])
        keyboard.extend(exclude_keyboard)
        
        # Clear buttons
        clear_buttons = []
        if content_filters["media_types"]["include"]:
            clear_buttons.append(InlineKeyboardButton("🗑️ Clear All Include", callback_data="del_include_media_all"))
        if content_filters["media_types"]["exclude"]:
            clear_buttons.append(InlineKeyboardButton("🗑️ Clear All Exclude", callback_data="del_exclude_media_all"))
        
        if clear_buttons:
            keyboard.append(clear_buttons)
            
        keyboard.append([InlineKeyboardButton("◀️ Back to Filters", callback_data="content_filters")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "add_include_media":
        # Show media type selection buttons instead of text input
        text = "🖼️ Select Media Type to Include\n\n" \
               "Only messages with these media types will be reposted.\n\n" \
               "Select a media type to add to the include list:"
               
        # Create buttons for each media type
        media_types = ["photo", "video", "document", "audio", "voice", "sticker", "animation"]
        keyboard = []
        
        # Create rows with 2 buttons each
        for i in range(0, len(media_types), 2):
            row = []
            row.append(InlineKeyboardButton(media_types[i], callback_data=f"toggle_include_media_{media_types[i]}"))
            if i + 1 < len(media_types):
                row.append(InlineKeyboardButton(media_types[i+1], callback_data=f"toggle_include_media_{media_types[i+1]}"))
            keyboard.append(row)
            
        # Add back button
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="media_filters")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_exclude_media":
        # Show media type selection buttons instead of text input
        text = "🖼️ Select Media Type to Exclude\n\n" \
               "Messages with these media types will NOT be reposted.\n\n" \
               "Select a media type to add to the exclude list:"
               
        # Create buttons for each media type
        media_types = ["photo", "video", "document", "audio", "voice", "sticker", "animation"]
        keyboard = []
        
        # Create rows with 2 buttons each
        for i in range(0, len(media_types), 2):
            row = []
            row.append(InlineKeyboardButton(media_types[i], callback_data=f"toggle_exclude_media_{media_types[i]}"))
            if i + 1 < len(media_types):
                row.append(InlineKeyboardButton(media_types[i+1], callback_data=f"toggle_exclude_media_{media_types[i+1]}"))
            keyboard.append(row)
            
        # Add back button
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="media_filters")])
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "remove_include_media":
        if not content_filters["media_types"]["include"]:
            await edit_message_smartly(
                query.message,
                "No include media types to remove.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="media_filters")]])
            )
            return
            
        # Create keyboard with buttons for each media type
        keyboard = []
        for media_type in content_filters["media_types"]["include"]:
            keyboard.append([InlineKeyboardButton(f"Remove: {media_type}", callback_data=f"del_include_media_{media_type}")])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="media_filters")])
        
        await edit_message_smartly(
            query.message,
            "Select an include media type to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "remove_exclude_media":
        if not content_filters["media_types"]["exclude"]:
            await edit_message_smartly(
                query.message,
                "No exclude media types to remove.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="media_filters")]])
            )
            return
            
        # Create keyboard with buttons for each media type
        keyboard = []
        for media_type in content_filters["media_types"]["exclude"]:
            keyboard.append([InlineKeyboardButton(f"Remove: {media_type}", callback_data=f"del_exclude_media_{media_type}")])
        keyboard.append([InlineKeyboardButton("◀️ Back", callback_data="media_filters")])
        
        await edit_message_smartly(
            query.message,
            "Select an exclude media type to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data.startswith("del_include_media_"):
        # Extract the media type from the callback data
        media_type = query.data[len("del_include_media_"):]
        
        if media_type in content_filters["media_types"]["include"]:
            content_filters["media_types"]["include"].remove(media_type)
            # Save the change to config
            BOT_CONFIG["filter_include_media"] = content_filters["media_types"]["include"]
            save_bot_config()
            await edit_message_smartly(
                query.message,
                f"Removed '{media_type}' from include media types.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]])
            )
        else:
            await edit_message_smartly(
                query.message,
                f"Media type '{media_type}' not found in include list.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="media_filters")]])
            )
    
    elif query.data.startswith("del_exclude_media_"):
        # Extract the media type from the callback data
        media_type = query.data[len("del_exclude_media_"):]
        
        if media_type in content_filters["media_types"]["exclude"]:
            content_filters["media_types"]["exclude"].remove(media_type)
            # Save the change to config
            BOT_CONFIG["filter_exclude_media"] = content_filters["media_types"]["exclude"]
            save_bot_config()
            await edit_message_smartly(
                query.message,
                f"Removed '{media_type}' from exclude media types.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]])
            )
        else:
            await edit_message_smartly(
                query.message,
                f"Media type '{media_type}' not found in exclude list.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="media_filters")]])
            )
    
    elif query.data.startswith("toggle_include_media_"):
        # Extract the media type from the callback data
        media_type = query.data[len("toggle_include_media_"):]
        
        # Add or remove the media type from the include list
        if media_type in content_filters["media_types"]["include"]:
            # Remove if already exists
            content_filters["media_types"]["include"].remove(media_type)
            status_msg = f"Removed '{media_type}' from include media types"
        else:
            # Add if doesn't exist
            content_filters["media_types"]["include"].append(media_type)
            status_msg = f"Added '{media_type}' to include media types"
        
        # Save the changes to config
        BOT_CONFIG["filter_include_media"] = content_filters["media_types"]["include"]
        save_bot_config()
        
        # Show notification
        await query.answer(status_msg)
        
        # Return to media filters menu to show updated state
        await edit_message_smartly(
            query.message,
            f"{status_msg}. Returning to media filters...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]])
        )
        
    elif query.data.startswith("toggle_exclude_media_"):
        # Extract the media type from the callback data
        media_type = query.data[len("toggle_exclude_media_"):]
        
        # Add or remove the media type from the exclude list
        if media_type in content_filters["media_types"]["exclude"]:
            # Remove if already exists
            content_filters["media_types"]["exclude"].remove(media_type)
            status_msg = f"Removed '{media_type}' from exclude media types"
        else:
            # Add if doesn't exist
            content_filters["media_types"]["exclude"].append(media_type)
            status_msg = f"Added '{media_type}' to exclude media types"
        
        # Save the changes to config
        BOT_CONFIG["filter_exclude_media"] = content_filters["media_types"]["exclude"]
        save_bot_config()
        
        # Show notification
        await query.answer(status_msg)
        
        # Return to media filters menu to show updated state
        await edit_message_smartly(
            query.message,
            f"{status_msg}. Returning to media filters...",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]])
        )
        
    elif query.data == "none_action":
        # This is just a label button, do nothing but show a notification
        await query.answer("This is just a label, not a button")
        
    elif query.data == "del_include_media_all":
        # Clear all include media types
        content_filters["media_types"]["include"] = []
        BOT_CONFIG["filter_include_media"] = []
        save_bot_config()
        await edit_message_smartly(
            query.message,
            "Cleared all include media types.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]]) 
        )
        
    elif query.data == "del_exclude_media_all":
        # Clear all exclude media types
        content_filters["media_types"]["exclude"] = []
        BOT_CONFIG["filter_exclude_media"] = []
        save_bot_config()
        await edit_message_smartly(
            query.message,
            "Cleared all exclude media types.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Media Filters", callback_data="media_filters")]]) 
        )
    
    elif query.data == "deletion_sync":
        # Show deletion sync options menu
        current_sync = BOT_CONFIG.get("sync_deletions", False)
        current_status = "✅ ON" if current_sync else "❌ OFF"
        
        # Create keyboard with ON and OFF buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Turn ON", callback_data="deletion_sync_on"),
                InlineKeyboardButton("❌ Turn OFF", callback_data="deletion_sync_off")
            ],
            [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]
        ]
        
        # Show the menu with current status and explanation
        await query.edit_message_text(
            f"🗑️ Deletion Synchronization Settings\n\n"
            f"Current status: {current_status}\n\n"
            f"When deletion sync is enabled, the bot will delete messages from destination channels "
            f"when the corresponding message is deleted from a source channel.\n\n"
            f"Note: The bot can only sync deletions for the last 3 messages due to memory constraints.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "deletion_sync_on":
        # Turn ON deletion sync
        BOT_CONFIG["sync_deletions"] = True
        sync_deletions = True
        
        # Save the setting
        save_bot_config()
        
        # Inform the user
        await query.edit_message_text(
            "🗑️ Deletion Synchronization has been turned ✅ ON.\n\n"
            "Messages deleted in source channels will now be deleted in destination channels.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Settings", callback_data="deletion_sync")],
                [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
            ])
        )
        
    elif query.data == "deletion_sync_off":
        # Turn OFF deletion sync
        BOT_CONFIG["sync_deletions"] = False
        sync_deletions = False
        
        # Save the setting
        save_bot_config()
        
        # Inform the user
        await query.edit_message_text(
            "🗑️ Deletion Synchronization has been turned ❌ OFF.\n\n"
            "Messages deleted in source channels will no longer be deleted in destination channels.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("◀️ Back to Settings", callback_data="deletion_sync")],
                [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
            ])
        )
    
    elif query.data == "set_destination":
        text = "🎯 Set Primary Destination Channel\n\n" \
               "Please send the channel identifier in any of these formats:\n\n" \
               "✅ Numeric ID: `-1001234567890`\n" \
               "✅ Username: `@channelname`\n" \
               "✅ Link: `https://t.me/channelname`\n\n" \
               "💡 Tip: Numeric IDs are the most reliable. You can get a channel's numeric ID " \
               "by forwarding any message from the channel to @userinfobot.\n\n" \
               "⚠️ Important: Make sure the bot is an admin in the destination channel with permission to post messages."
               
        buttons = InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="back_to_menu")]])
        
        # Use our helper function to smartly edit the message
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=buttons,
            parse_mode="HTML"
        )
        
        context.user_data["awaiting"] = "destination_channel"
    
    elif query.data == "toggle_clean_mode":
        # Toggle clean mode setting
        current_mode = BOT_CONFIG.get("CLEAN_MODE", "false").lower() == "true"
        new_mode = not current_mode
        
        # Update the config
        BOT_CONFIG["CLEAN_MODE"] = str(new_mode).lower()
        
        # Save the updated configuration
        save_bot_config()
        
        # Notify the user of the change
        await query.edit_message_text(
            f"✅ Clean Mode has been {'enabled' if new_mode else 'disabled'}.\n\n" +
            ("When enabled, channel tags and mentions will be completely removed instead of replaced." if new_mode else 
            "When disabled, channel tags and mentions will be replaced with destination channel information."),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
        )
    
    elif query.data == "view_config":
        source_text_items = []
        if active_channels["source"]:
            for ch in active_channels["source"]:
                info = await get_entity_info(user_client, ch)
                if info:
                    title = info.get("title", str(ch))
                    source_text_items.append(f"• {title}")
                else:
                    source_text_items.append(f"• {str(ch)}")
            source_text = "\n".join(source_text_items)
        else:
            source_text = "None"
            
        destination_info = None
        if active_channels["destination"]:
            destination_info = await get_entity_info(user_client, active_channels["destination"])
            
        destination_text = "None"
        if destination_info:
            destination_text = destination_info.get("title", str(active_channels["destination"]))
            
        # Add tag replacement configuration
        tag_text_items = []
        if tag_replacements:
            for old_tag, new_tag in tag_replacements.items():
                tag_text_items.append(f"• {old_tag} → {new_tag}")
            tag_text = "\n".join(tag_text_items)
        else:
            tag_text = "None"
            
        # Add clean mode status
        clean_mode = BOT_CONFIG.get("CLEAN_MODE", "false").lower() == "true"
        clean_mode_text = "✅ Enabled" if clean_mode else "❌ Disabled"
        
        # Get reposting status
        reposting_status = "✅ Active" if reposting_active else "❌ Inactive"
        
        # Add action buttons specific to configuration viewing
        action_buttons = []
        
        # Add channel management buttons
        if active_channels["source"]:
            action_buttons.append([InlineKeyboardButton("➖ Remove Source Channels", callback_data="remove_source")])
        
        if active_channels["destination"]:
            action_buttons.append([InlineKeyboardButton("🗑️ Remove Destination Channel", callback_data="remove_destination")])
        
        # Add tag management button if there are tags
        if tag_replacements:
            action_buttons.append([InlineKeyboardButton("🏷️ Manage Tags", callback_data="manage_tags")])
        
        # Always add back button
        action_buttons.append([InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            f"📊 Current Configuration\n\n"
            f"📡 Source Channels:\n{source_text}\n\n"
            f"🎯 Destination Channel:\n{destination_text}\n\n"
            f"🏷️ Tag Replacements:\n{tag_text}\n\n"
            f"🧹 Clean Mode: {clean_mode_text}\n\n"
            f"⚙️ Reposting Status: {reposting_status}",
            reply_markup=InlineKeyboardMarkup(action_buttons)
        )
    
    elif query.data == "manage_tags":
        # Build a more useful menu showing current tags with add/remove options
        
        # Get destination channel info for auto-suggestion
        destination_tag = None
        if active_channels["destination"]:
            try:
                dest_info = await get_entity_info(user_client, active_channels["destination"])
                if dest_info and dest_info.get("username"):
                    destination_tag = f"@{dest_info['username']}"
            except Exception as e:
                logger.error(f"Error getting destination tag: {str(e)}")
        
        # Create main action buttons
        action_buttons = [
            [
                InlineKeyboardButton("➕ Add Tag", callback_data="add_tag"),
                InlineKeyboardButton("➖ Remove Tag", callback_data="remove_tag")
            ]
        ]
        
        # Show current tag replacements if any exist
        current_tags_text = ""
        if tag_replacements:
            current_tags_text = "\n\nCurrent Tag Replacements:\n"
            for old_tag, new_tag in tag_replacements.items():
                current_tags_text += f"• {old_tag} → {new_tag}\n"
        
        # Add a helper button if destination channel has a username
        helper_buttons = []
        if destination_tag:
            helper_text = f"Destination channel tag: {destination_tag}"
            helper_buttons = [
                [InlineKeyboardButton(f"Auto-add common formats for {destination_tag}", callback_data="auto_add_tags")]
            ]
        
        # Back button
        back_button = [[InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_menu")]]
        
        # Combine all buttons
        keyboard = []
        keyboard.extend(action_buttons)
        if helper_buttons:
            keyboard.extend(helper_buttons)
        keyboard.extend(back_button)
        
        await query.edit_message_text(
            "🏷️ Tag Replacement Management\n\n"
            "Replace channel tags in messages during reposting to make content "
            "appear as if it originated from your destination channel.\n\n"
            "Supported formats:\n"
            "• @username mentions\n"
            "• t.me/username links\n"
            "• https://t.me/username links\n"
            "• telegram.me/username links" + 
            current_tags_text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_tag":
        await query.edit_message_text(
            "Please send the tag you want to replace in the format:\n\n"
            "`old_tag → new_tag`\n\n"
            "Examples:\n"
            "- `@channel1 → @my_channel`\n"
            "- `t.me/original → t.me/replacement`"
        )
        context.user_data["awaiting"] = "tag_replacement"
    
    elif query.data == "remove_tag":
        if not tag_replacements:
            await query.edit_message_text(
                "❌ No tag replacements configured yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Tags", callback_data="manage_tags")]])
            )
            return
        
        keyboard = []
        for old_tag, new_tag in tag_replacements.items():
            keyboard.append([InlineKeyboardButton(f"🗑️ {old_tag} → {new_tag}", callback_data=f"remove_tag_{old_tag}")])
        
        keyboard.append([InlineKeyboardButton("◀️ Back to Tags", callback_data="manage_tags")])
        await query.edit_message_text(
            "🏷️ Select a tag replacement to remove:\n\n"
            "Click on a tag to remove it from the replacement list.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("remove_tag_"):
        old_tag = query.data[11:]  # Remove "remove_tag_" prefix
        if old_tag in tag_replacements:
            # Get the value before deleting
            removed_value = tag_replacements[old_tag]
            del tag_replacements[old_tag]
            await save_tag_config()
            await query.edit_message_text(
                f"✅ Tag replacement removed:\n\n"
                f"🔄 {old_tag} → {removed_value}\n\n"
                f"The tag will no longer be replaced in messages.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Tags", callback_data="manage_tags")],
                    [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                "❌ Tag replacement not found.\n\n"
                "The tag may have been already removed or never existed.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Back to Tags", callback_data="manage_tags")]
                ])
            )
    
    elif query.data == "delete_session":
        # Confirm before deleting the session
        confirm_keyboard = [
            [
                InlineKeyboardButton("Yes, delete session", callback_data="confirm_delete_session"),
                InlineKeyboardButton("No, cancel", callback_data="config_api")
            ]
        ]
        
        await query.edit_message_text(
            "⚠️ Are you sure you want to delete the current user session?\n\n"
            "This will remove the USER_SESSION from your configuration. "
            "You will need to generate a new session to use the reposting functionality.",
            reply_markup=InlineKeyboardMarkup(confirm_keyboard)
        )
    
    elif query.data == "confirm_delete_session":
        # Delete the session
        global USER_SESSION
        USER_SESSION = None
        
        # Remove from environment
        if "USER_SESSION" in os.environ:
            del os.environ["USER_SESSION"]
        
        # Update the .env file by removing the USER_SESSION line
        try:
            env_file_path = ".env"
            # Read the file
            if os.path.exists(env_file_path):
                with open(env_file_path, "r") as file:
                    lines = file.readlines()
                
                # Filter out the USER_SESSION line
                lines = [line for line in lines if not line.strip().startswith("USER_SESSION=")]
                
                # Write the updated content back
                with open(env_file_path, "w") as file:
                    file.writelines(lines)
                
                await query.edit_message_text(
                    "✅ User session has been successfully deleted.\n\n"
                    "You will need to generate a new session to use the reposting functionality.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
                )
            else:
                await query.edit_message_text(
                    "❌ Could not find the .env file to update.\n\n"
                    "The session has been removed from the current runtime.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
                )
        except Exception as e:
            logger.error(f"Error updating .env file: {str(e)}")
            await query.edit_message_text(
                f"❌ Error updating .env file: {str(e)}\n\n"
                "The session has been removed from the current runtime.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
            )
    
    elif query.data == "add_session":
        # Redirect to generating a new session
        await query.edit_message_text(
            "To add a new session, you need to run the gen_session.py script.\n\n"
            "1. Run the script in a terminal: `python gen_session.py`\n"
            "2. Follow the prompts to log in with your phone number\n"
            "3. Enter the verification code when prompted\n"
            "4. Copy the generated session string\n"
            "5. Use the 'Set USER_SESSION' button to add the session\n\n"
            "Would you like to proceed?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Generate Session Now", callback_data="set_user_session")],
                [InlineKeyboardButton("Back to API Config", callback_data="config_api")]
            ])
        )
    
    elif query.data == "remove_destination":
        # Confirm before removing the destination
        if not active_channels["destination"]:
            await query.edit_message_text(
                "No destination channel is currently configured.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
            )
            return
        
        # Try to get destination channel info
        destination_name = str(active_channels["destination"])
        try:
            info = await get_entity_info(user_client, active_channels["destination"])
            if info and info.get("title"):
                destination_name = info.get("title")
        except Exception as e:
            logger.error(f"Error getting destination channel info: {str(e)}")
        
        confirm_keyboard = [
            [
                InlineKeyboardButton("Yes, remove it", callback_data="confirm_remove_destination"),
                InlineKeyboardButton("No, keep it", callback_data="back_to_menu")
            ]
        ]
        
        await query.edit_message_text(
            f"⚠️ Are you sure you want to remove the destination channel?\n\n"
            f"Current destination: {destination_name}\n\n"
            f"You will need to set a new destination channel to use the reposting functionality.",
            reply_markup=InlineKeyboardMarkup(confirm_keyboard)
        )
    
    elif query.data == "confirm_remove_destination":
        # Remove the destination channel
        old_destination = active_channels["destination"]
        active_channels["destination"] = None
        
        # Save the updated configuration
        await save_config()
        
        await query.edit_message_text(
            f"✅ Destination channel has been removed successfully.\n\n"
            f"You will need to set a new destination channel to use the reposting functionality.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
        )
    
    elif query.data == "start_reposting":
        if not active_channels["source"] or not active_channels["destination"]:
            await query.edit_message_text(
                "❌ Cannot start reposting. Please configure at least one source channel and a destination channel.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
            return
        
        # Start listening for new messages
        if not reposting_active:
            # Set reposting_active at the module level
            reposting_active = True
            # Save reposting state to config
            save_reposting_state()
            
            # Get human-readable channel names for the confirmation message
            source_names = []
            for ch_id in active_channels["source"]:
                try:
                    info = await get_entity_info(user_client, ch_id)
                    if info and info.get("title"):
                        source_names.append(info.get("title"))
                    else:
                        source_names.append(str(ch_id))
                except:
                    source_names.append(str(ch_id))
            
            dest_name = str(active_channels["destination"])
            try:
                info = await get_entity_info(user_client, active_channels["destination"])
                if info and info.get("title"):
                    dest_name = info.get("title")
            except:
                pass
            
            # Force update the event handlers for source channels
            await save_config()
            
            # Build tag replacement info for message
            tag_info = ""
            if tag_replacements:
                tag_info = f"\n\nTag replacements are active for {len(tag_replacements)} tags."
            
            await query.edit_message_text(
                f"✅ Started reposting from {len(active_channels['source'])} source channel(s) to {dest_name}.\n\n"
                f"📡 Source channels: {', '.join(source_names)}{tag_info}\n\n"
                "🔄 New messages will now be automatically reposted.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏹️ Stop Reposting", callback_data="stop_reposting")],
                    [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                "ℹ️ Reposting is already active. If you're not seeing posts being reposted, try stopping and starting again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("⏹️ Stop Reposting", callback_data="stop_reposting")],
                    [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]
                ])
            )
    
    elif query.data == "stop_reposting":
        if reposting_active:
            reposting_active = False
            # Save reposting state to config
            save_reposting_state()
            await query.edit_message_text(
                "⏹️ Stopped reposting from source channels.\n\n"
                "No more messages will be reposted until you start the service again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Start Reposting", callback_data="start_reposting")],
                    [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]
                ])
            )
        else:
            await query.edit_message_text(
                "ℹ️ Reposting is not currently active.\n\n"
                "Use the Start Reposting button to activate the service.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("▶️ Start Reposting", callback_data="start_reposting")],
                    [InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]
                ])
            )
    
    elif query.data == "channel_settings_menu":
        # Channel management hub - Independent from source/destination functionality
        text = "⚙️ Channel Management\n\n"
        text += "Manage any Telegram channel, independent from reposting functionality.\n\n"
        text += "Select an option:"
        
        # Organize options into logical groups
        keyboard = [
            # Channel Discovery/Management
            [InlineKeyboardButton("📋 View My Channels", callback_data="list_my_channels")],
            
            # Channel Maintenance Tools
            [InlineKeyboardButton("🧹 Channel Cleanup Tools", callback_data="channel_cleanup_menu")],
            [InlineKeyboardButton("📊 View Current Settings", callback_data="view_channel_settings")],
            
            # Navigation
            [InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "view_channel_settings":
        # View current channel management settings
        text = "📊 Channel Management Settings\n\n"
        
        # Display farewell sticker info
        text += f"🎭 Farewell Stickers:\n"
        if len(FAREWELL_STICKERS) > 1:
            text += f"✅ You have {len(FAREWELL_STICKERS)} stickers configured.\n"
            text += f"The bot will randomly select one when leaving a channel.\n\n"
        elif len(FAREWELL_STICKERS) == 1:
            text += f"✅ You have 1 sticker configured.\n\n"
        else:
            text += f"❌ No stickers configured.\n\n"
        
        # Add helpful information
        text += "ℹ️ A farewell sticker will be sent before leaving a channel when using the 'Delete & Leave' feature.\n\n"
        text += "To manage stickers, use `python set_farewell_sticker_input.py` in the Replit terminal."
        
        keyboard = [
            [InlineKeyboardButton("◀️ Back to Settings", callback_data="channel_settings_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
    elif query.data == "set_farewell_sticker":
        # Show options for setting farewell sticker
        text = "🎭 Set Farewell Sticker\n\n"
        text += "This sticker will be posted before the bot leaves a channel when using the 'Delete & Leave' feature.\n\n"
        
        # Show info about current stickers
        current_sticker_count = len(FAREWELL_STICKERS)
        if current_sticker_count > 1:
            text += f"✨ You currently have {current_sticker_count} farewell stickers that will be randomly rotated.\n\n"
        elif current_sticker_count == 1:
            text += "✨ You currently have 1 farewell sticker configured.\n\n"
        
        text += "Choose an option:\n\n"
        
        keyboard = [
            [InlineKeyboardButton("➕ Add Sticker to Collection", callback_data="add_farewell_sticker")],
            [InlineKeyboardButton("🔄 Replace All Stickers", callback_data="replace_farewell_stickers")],
            [InlineKeyboardButton("👀 View Current Stickers", callback_data="view_farewell_stickers")],
            [InlineKeyboardButton("◀️ Back", callback_data="view_channel_settings")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "add_farewell_sticker":
        # Add a new sticker to the collection - USE MANUAL INPUT INSTEAD
        text = "➕ Add Sticker to Collection\n\n"
        text += "Due to a technical issue with direct sticker input, please use this alternative method:\n\n"
        text += "1. Send a sticker directly to @idstickerbot to get its ID\n"
        text += "2. Copy the sticker ID (long text starting with 'CAA...')\n"
        text += "3. Run this command in your Replit terminal:\n"
        text += "   ```\n"
        text += "   python set_farewell_sticker_input.py \"STICKER_ID_HERE\" add\n"
        text += "   ```\n\n"
        text += "After running the command, your sticker will be added to the farewell collection."
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="set_farewell_sticker")]])
        )
        
    elif query.data == "replace_farewell_stickers":
        # Replace all stickers with a new one
        text = "🔄 Replace All Stickers\n\n"
        text += "Due to a technical issue with direct sticker input, please use this alternative method:\n\n"
        text += "1. Send a sticker directly to @idstickerbot to get its ID\n"
        text += "2. Copy the sticker ID (long text starting with 'CAA...')\n"
        text += "3. Run this command in your Replit terminal:\n"
        text += "   ```\n"
        text += "   python set_farewell_sticker_input.py \"STICKER_ID_HERE\" replace\n"
        text += "   ```\n\n"
        text += "⚠️ WARNING: Using the 'replace' option will remove all your previously configured farewell stickers!"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="set_farewell_sticker")]])
        )
        
    elif query.data == "view_farewell_stickers":
        # View all current farewell stickers
        text = "👀 Current Farewell Stickers\n\n"
        
        sticker_count = len(FAREWELL_STICKERS)
        
        if sticker_count == 0:
            text += "You don't have any farewell stickers configured yet."
        elif sticker_count == 1:
            text += "You have 1 farewell sticker configured.\n"
            text += "This sticker will be sent before leaving a channel."
        else:
            text += f"You have {sticker_count} farewell stickers configured.\n"
            text += "The bot will randomly choose one when leaving a channel."
        
        # Try to send the current sticker(s) as preview
        if sticker_count > 0:
            try:
                # First save this message
                response = await query.edit_message_text(
                    text + "\n\nSending sticker previews...",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="set_farewell_sticker")]])
                )
                
                # Send each sticker as a separate message
                for i, sticker_id in enumerate(FAREWELL_STICKERS):
                    try:
                        # Send the sticker with a caption showing its position
                        await query.message.chat.send_sticker(
                            sticker=sticker_id,
                            reply_to_message_id=response.message_id
                        )
                        # Brief delay to avoid hitting rate limits
                        await asyncio.sleep(0.5)
                    except Exception as e:
                        logger.error(f"Error sending sticker preview {i+1}/{sticker_count}: {e}")
                        
                # Update the text to indicate we're done
                await query.edit_message_text(
                    text + "\n\nSticker previews sent above ☝️",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="set_farewell_sticker")]])
                )
            except Exception as e:
                logger.error(f"Error in sticker preview: {e}")
                # Fallback - just send the basic info
                await query.edit_message_text(
                    text + "\n\nCouldn't send sticker previews.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="set_farewell_sticker")]])
                )
        else:
            # No stickers to preview
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="set_farewell_sticker")]])
            )
        
    elif query.data == "list_my_channels":
        # List all channels the user is part of
        text = "📋 My Telegram Channels\n\n"
        text += "Loading your channels...\n\n"
        text += "Please wait..."
        
        status_msg = await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="channel_settings_menu")]])
        )
        
        # Fetch all dialogs (channels, groups, chats) using the user client
        try:
            if not user_client or not user_client.is_connected():
                await status_msg.edit_text(
                    "❌ Error: User client not connected\n\n"
                    "Please set up a user session first.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("➕ Add Session", callback_data="add_session")],
                        [InlineKeyboardButton("◀️ Back", callback_data="channel_settings_menu")]
                    ])
                )
                return
                
            text = "📋 My Telegram Channels\n\n"
            dialogs = await user_client.get_dialogs()
            
            channels = []
            groups = []
            supergroups = []
            
            # Categorize dialogs
            for dialog in dialogs:
                if dialog.is_channel:
                    if dialog.entity.broadcast:
                        channels.append(dialog)
                    else:
                        supergroups.append(dialog)
                elif dialog.is_group:
                    groups.append(dialog)
            
            # Format channels list
            if channels:
                text += "📢 Broadcast Channels:\n"
                for idx, channel in enumerate(channels, 1):
                    entity = channel.entity
                    title = getattr(entity, 'title', 'Unnamed')
                    channel_id = entity.id
                    username = getattr(entity, 'username', None)
                    username_str = f" (@{username})" if username else ""
                    text += f"{idx}. {title}{username_str}\n   ID: {channel_id}\n"
            else:
                text += "📢 Broadcast Channels: None\n"
            
            # Format supergroups list
            if supergroups:
                text += "\n👥 Supergroups:\n"
                for idx, group in enumerate(supergroups, 1):
                    entity = group.entity
                    title = getattr(entity, 'title', 'Unnamed')
                    group_id = entity.id
                    username = getattr(entity, 'username', None)
                    username_str = f" (@{username})" if username else ""
                    text += f"{idx}. {title}{username_str}\n   ID: {group_id}\n"
            else:
                text += "\n👥 Supergroups: None\n"
            
            # Format groups list
            if groups:
                text += "\n👪 Regular Groups:\n"
                for idx, group in enumerate(groups, 1):
                    entity = group.entity
                    title = getattr(entity, 'title', 'Unnamed')
                    group_id = entity.id
                    text += f"{idx}. {title}\n   ID: {group_id}\n"
            else:
                text += "\n👪 Regular Groups: None\n"
            
            if not channels and not groups and not supergroups:
                text += "\n❌ You're not a member of any channels or groups."
                
            # Add note about IDs
            text += "\n\nℹ️ You can use these channel IDs for channel management operations."
            
        except Exception as e:
            text = f"❌ Error fetching channels: {str(e)}\n\n"
            text += "Please make sure you have a valid user session."
            
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh List", callback_data="list_my_channels")],
            [InlineKeyboardButton("◀️ Back to Channel Settings", callback_data="channel_settings_menu")],
            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
        ]
        
        await status_msg.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "list_all_channels":
        # List all configured channels for reposting
        text = "📋 Reposting Channels\n\n"
        text += "These are the channels configured for the reposting functionality:\n\n"
        
        # List source channels
        text += "📥 Source Channels:\n"
        if active_channels["source"]:
            for idx, channel in enumerate(active_channels["source"], 1):
                info = await get_entity_info(user_client, channel)
                display_name = info.get("title", str(channel)) if info else str(channel)
                text += f"{idx}. {display_name} (ID: {channel})\n"
        else:
            text += "None configured\n"
        
        # List main destination channel
        text += "\n🎯 Primary Destination Channel:\n"
        if active_channels["destination"]:
            info = await get_entity_info(user_client, active_channels["destination"])
            display_name = info.get("title", str(active_channels["destination"])) if info else str(active_channels["destination"])
            text += f"{display_name} (ID: {active_channels['destination']})\n"
        else:
            text += "None configured\n"
        
        # List additional destination channels
        text += "\n📨 Additional Destination Channels:\n"
        if active_channels["destinations"]:
            for idx, channel in enumerate(active_channels["destinations"], 1):
                info = await get_entity_info(user_client, channel)
                display_name = info.get("title", str(channel)) if info else str(channel)
                text += f"{idx}. {display_name} (ID: {channel})\n"
        else:
            text += "None configured\n"
        
        keyboard = [
            [InlineKeyboardButton("◀️ Back to Channel Settings", callback_data="channel_settings_menu")],
            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "add_channel_management":
        # Add/join channel - Independent from reposting functionality
        text = "➕ Add or Join Channel\n\n"
        text += "What would you like to do?"
        
        keyboard = [
            [InlineKeyboardButton("🔍 Join Existing Channel", callback_data="join_any_channel")],
            [InlineKeyboardButton("📥 Add as Source Channel", callback_data="add_source")],
            [InlineKeyboardButton("🎯 Add as Destination Channel", callback_data="set_destination")],
            [InlineKeyboardButton("◀️ Back to Channel Management", callback_data="channel_settings_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "join_any_channel":
        # Join any channel (not necessarily for reposting)
        text = "🔍 Join a Channel\n\n"
        text += "Please send the channel identifier in any of these formats:\n\n"
        text += "✅ Channel Link: `https://t.me/channelname`\n"
        text += "✅ Invite Link: `https://t.me/joinchat/abcdef...`\n"
        text += "✅ Username: `@channelname`\n"
        text += "✅ Numeric ID: `-1001234567890`\n\n"
        text += "The bot will attempt to join this channel for you."
        
        keyboard = [[InlineKeyboardButton("◀️ Cancel", callback_data="add_channel_management")]]
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        context.user_data["awaiting"] = "join_any_channel_input"
        
    elif query.data == "channel_cleanup_menu":
        # Channel cleanup tools menu
        text = "🧹 Channel Cleanup Tools\n\n"
        text += "These tools allow you to clean up and manage any Telegram channel.\n\n"
        text += "Select an option:"
        
        keyboard = [
            [InlineKeyboardButton("🗑️ Delete All Messages", callback_data="purge_channel_menu")],
            [InlineKeyboardButton("🚪 Delete & Leave Channel", callback_data="purge_and_leave_menu")],
            [InlineKeyboardButton("◀️ Back to Channel Management", callback_data="channel_settings_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "purge_channel_menu":
        # Channel purge menu
        text = "🗑️ Channel Message Purge\n\n"
        text += "This tool allows you to delete ALL messages from a channel.\n\n"
        text += "⚠️ WARNING: This is a destructive operation that cannot be undone!\n"
        text += "All messages in the selected channel will be permanently deleted.\n\n"
        text += "Requirements:\n"
        text += "• The bot must be an admin in the channel\n"
        text += "• The bot must have 'Delete Messages' permission\n\n"
        text += "Please select an option:"
        
        keyboard = [
            [InlineKeyboardButton("📋 Select from Existing Channels", callback_data="purge_existing_channel")],
            [InlineKeyboardButton("🔄 Enter New Channel to Purge", callback_data="enter_purge_channel")],
            [InlineKeyboardButton("◀️ Back to Cleanup Tools", callback_data="channel_cleanup_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "purge_and_leave_menu":
        # Purge and leave menu
        text = "🚪 Delete All Messages & Leave Channel\n\n"
        text += "This tool will:\n"
        text += "1. Delete ALL messages from the channel\n"
        text += "2. Send a farewell sticker\n"
        text += "3. Leave the channel\n\n"
        text += "⚠️ WARNING: This is a destructive operation that cannot be undone!\n\n"
        text += "Requirements:\n"
        text += "• The bot must be an admin in the channel\n"
        text += "• The bot must have necessary permissions\n\n"
        text += "Please select an option:"
        
        keyboard = [
            [InlineKeyboardButton("📋 Select Existing Channel", callback_data="purge_leave_existing")],
            [InlineKeyboardButton("🔄 Enter New Channel", callback_data="enter_purge_leave_channel")],
            [InlineKeyboardButton("◀️ Back to Cleanup Tools", callback_data="channel_cleanup_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "purge_existing_channel" or query.data == "purge_leave_existing":
        # The action depends on which menu we came from
        purge_and_leave = (query.data == "purge_leave_existing")
        
        if purge_and_leave:
            text = "Select a channel to delete ALL messages and leave:\n\n"
            return_callback = "purge_and_leave_menu"
            confirm_prefix = "confirm_purge_leave_"
        else:
            text = "Select a channel to delete ALL messages:\n\n"
            return_callback = "purge_channel_menu"
            confirm_prefix = "confirm_purge_"
            
        text += "⚠️ WARNING: All messages will be permanently deleted!\n\n"
        text += "Choose any channel where you are an admin:"
        
        keyboard = []
        
        # Get list of available channels from telethon client
        try:
            # List channels where the user is an admin
            dialogs = await user_client.get_dialogs()
            channels_added = 0
            
            for dialog in dialogs:
                # Check if it's a channel or supergroup
                if dialog.is_channel or dialog.is_group:
                    try:
                        entity = dialog.entity
                        # Get entity info to display name
                        channel_id = entity.id
                        display_name = getattr(entity, 'title', str(channel_id))
                        
                        # Add to keyboard
                        keyboard.append([
                            InlineKeyboardButton(
                                f"🗑️ {display_name}", 
                                callback_data=f"{confirm_prefix}{channel_id}"
                            )
                        ])
                        channels_added += 1
                    except Exception as e:
                        logger.error(f"Error adding channel to list: {str(e)}")
                        
            # Add back button
            keyboard.append([InlineKeyboardButton("◀️ Back", callback_data=return_callback)])
            
            # If no channels are available
            if channels_added == 0:
                text = "No channels available.\n\n"
                text += "Please enter a new channel identifier instead."
                if purge_and_leave:
                    keyboard = [
                        [InlineKeyboardButton("🔄 Enter Channel ID/Username", callback_data="enter_purge_leave_channel")],
                        [InlineKeyboardButton("◀️ Back", callback_data=return_callback)]
                    ]
                else:
                    keyboard = [
                        [InlineKeyboardButton("🔄 Enter Channel ID/Username", callback_data="enter_purge_channel")],
                        [InlineKeyboardButton("◀️ Back", callback_data=return_callback)]
                    ]
        except Exception as e:
            text = f"Error retrieving channel list: {str(e)}\n\n"
            text += "Please enter a channel ID manually."
            if purge_and_leave:
                keyboard = [
                    [InlineKeyboardButton("🔄 Enter Channel ID/Username", callback_data="enter_purge_leave_channel")],
                    [InlineKeyboardButton("◀️ Back", callback_data=return_callback)]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("🔄 Enter Channel ID/Username", callback_data="enter_purge_channel")],
                    [InlineKeyboardButton("◀️ Back", callback_data=return_callback)]
                ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif query.data == "enter_purge_channel" or query.data == "enter_purge_leave_channel":
        # The action depends on which menu we came from
        purge_and_leave = (query.data == "enter_purge_leave_channel")
        
        if purge_and_leave:
            text = "🚪 Enter Channel to Purge and Leave\n\n"
            return_callback = "purge_and_leave_menu"
            awaiting_state = "purge_leave_channel_input"
        else:
            text = "🗑️ Enter Channel to Purge\n\n"
            return_callback = "purge_channel_menu"
            awaiting_state = "purge_channel_input"
            
        text += "Please send the channel identifier in any of these formats:\n\n"
        text += "✅ Numeric ID: `-1001234567890`\n"
        text += "✅ Username: `@channelname`\n"
        text += "✅ Link: `https://t.me/channelname`\n\n"
        text += "⚠️ IMPORTANT: The bot must be an admin with necessary permissions in this channel."
        
        keyboard = [[InlineKeyboardButton("◀️ Cancel", callback_data=return_callback)]]
        
        await edit_message_smartly(
            query.message,
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        
        context.user_data["awaiting"] = awaiting_state
        
    elif query.data.startswith("confirm_purge_") or query.data.startswith("confirm_purge_leave_"):
        # Extract channel ID and action type
        purge_and_leave = query.data.startswith("confirm_purge_leave_")
        
        try:
            parts = query.data.split("_")
            if purge_and_leave:
                channel_id = int(parts[3])
                return_callback = "purge_and_leave_menu"
                execute_callback = f"execute_purge_leave_{channel_id}"
            else:
                channel_id = int(parts[2])
                return_callback = "purge_channel_menu"
                execute_callback = f"execute_purge_{channel_id}"
            
            # Get channel info
            info = await get_entity_info(user_client, channel_id)
            display_name = info.get("title", str(channel_id)) if info else str(channel_id)
            
            text = f"⚠️ FINAL WARNING ⚠️\n\n"
            if purge_and_leave:
                text += f"You are about to delete ALL messages and leave:\n"
            else:
                text += f"You are about to delete ALL messages from:\n"
            text += f"Channel: {display_name}\n"
            text += f"ID: {channel_id}\n\n"
            text += f"This action is IRREVERSIBLE and cannot be undone!\n\n"
            if purge_and_leave:
                text += f"The bot will delete all messages, post a farewell sticker, and leave the channel.\n\n"
            
            text += f"Are you absolutely sure you want to proceed?"
            
            keyboard = [
                [
                    InlineKeyboardButton("✅ YES, PROCEED", callback_data=execute_callback),
                ],
                [InlineKeyboardButton("❌ NO, CANCEL", callback_data=return_callback)]
            ]
            
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except ValueError:
            await query.edit_message_text(
                "Invalid channel ID format.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data=return_callback)]])
            )
            
    elif query.data.startswith("execute_purge_") or query.data.startswith("execute_purge_leave_"):
        # Extract action type and channel ID 
        purge_and_leave = query.data.startswith("execute_purge_leave_")
        
        try:
            parts = query.data.split("_")
            if purge_and_leave:
                channel_id = int(parts[3])
                return_callback = "purge_and_leave_menu"
            else:
                channel_id = int(parts[2])
                return_callback = "purge_channel_menu"
            
            # Start the purge process
            if purge_and_leave:
                await query.edit_message_text(
                    "🚪 Channel purge and leave in progress...\n\n"
                    "This may take a while depending on the number of messages.\n"
                    "Please do not interrupt this process.\n\n"
                    "Status: Starting purge..."
                )
            else:
                await query.edit_message_text(
                    "🗑️ Channel purge in progress...\n\n"
                    "This may take a while depending on the number of messages.\n"
                    "Please do not interrupt this process.\n\n"
                    "Status: Starting purge..."
                )
            
            # Check if bot has admin rights in the channel
            try:
                # Try to get channel entity first
                channel_entity = await user_client.get_entity(channel_id)
                
                # Send initial status message
                status_msg = await query.edit_message_text(
                    "🗑️ Channel purge in progress...\n\n"
                    "Checking admin permissions...\n"
                    "Please wait..."
                )
                
                # Attempt to purge messages
                deleted_count = 0
                
                # Start deleting messages
                try:
                    await status_msg.edit_text(
                        "🗑️ Channel purge in progress...\n\n"
                        f"Deleting messages...\n"
                        f"Deleted: {deleted_count} messages\n\n"
                        "This may take a long time for channels with many messages."
                    )
                    
                    # Check admin rights first
                    admin_rights_checked = False
                    is_admin = False
                    has_delete_permission = False
                    
                    try:
                        # First try a simple permission check by attempting to delete a single message
                        # This is more reliable than checking admin lists in many cases
                        test_messages = await user_client.get_messages(channel_entity, limit=1)
                        if test_messages and len(test_messages) > 0:
                            test_message = test_messages[0]
                            # Don't actually try deleting yet, just check admin status first
                            try:
                                # Get admin participants list first
                                me = await user_client.get_me()
                                my_id = me.id
                                
                                # Try to get admin participants list
                                participants = await user_client(GetParticipantsRequest(
                                    channel=channel_entity,
                                    filter=ChannelParticipantsAdmins(),
                                    offset=0,
                                    limit=100,
                                    hash=0
                                ))
                                
                                # Check if we're in the admin list
                                found_as_admin = False
                                for participant in participants.participants:
                                    if hasattr(participant, 'user_id') and participant.user_id == my_id:
                                        found_as_admin = True
                                        # Check for delete messages permission if possible
                                        if hasattr(participant, 'admin_rights') and hasattr(participant.admin_rights, 'delete_messages'):
                                            has_delete_permission = participant.admin_rights.delete_messages
                                        break
                                
                                if not found_as_admin:
                                    # We're definitively not an admin
                                    is_admin = False
                                    has_delete_permission = False
                                    admin_rights_checked = True
                                    
                                    await status_msg.edit_text(
                                        "⚠️ Admin Check Failed!\n\n"
                                        "You are not an admin in this channel.\n\n"
                                        "Add your user account as an admin with 'Delete Messages' permission first.",
                                        reply_markup=InlineKeyboardMarkup([
                                            [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                        ])
                                    )
                                    return
                                elif not has_delete_permission:
                                    # We're an admin but don't have delete permission
                                    is_admin = True
                                    admin_rights_checked = True
                                    
                                    await status_msg.edit_text(
                                        "⚠️ Permission Error!\n\n"
                                        "Your admin account doesn't have 'Delete Messages' permission.\n\n"
                                        "Please update your permissions for this channel.",
                                        reply_markup=InlineKeyboardMarkup([
                                            [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                        ])
                                    )
                                    return
                                
                                # Now that we know we're an admin with permissions, try deleting a test message
                                try:
                                    # Try deleting and immediately catch specific errors
                                    await user_client.delete_messages(channel_entity, test_message.id)
                                    # If we get here, we have delete permission confirmed
                                    is_admin = True
                                    has_delete_permission = True
                                    admin_rights_checked = True
                                    deleted_count += 1  # Count this test deletion
                                    logger.info("Admin rights confirmed through successful test deletion")
                                    
                                    await status_msg.edit_text(
                                        "✅ Admin rights confirmed!\n\n"
                                        "Starting message deletion..."
                                    )
                                    await asyncio.sleep(1)
                                except Exception as delete_test_error:
                                    # Failed to delete even though we should have permission
                                    logger.error(f"Error in test deletion despite admin status: {str(delete_test_error)}")
                                    await status_msg.edit_text(
                                        "⚠️ Error in Admin Check!\n\n"
                                        f"You have admin rights but couldn't delete messages: {str(delete_test_error)}\n\n"
                                        "This might be due to channel settings or restrictions.",
                                        reply_markup=InlineKeyboardMarkup([
                                            [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                        ])
                                    )
                                    return
                            except Exception as admin_check_error:
                                logger.error(f"Error checking admin status: {str(admin_check_error)}")
                                # Continue to the next method
                            except ChatAdminRequiredError:
                                # This specific error means we're not an admin
                                is_admin = False
                                admin_rights_checked = True
                                logger.info("Admin check failed: User is not an admin in this channel")
                                
                                await status_msg.edit_text(
                                    "⚠️ Permission Error!\n\n"
                                    "You are not an admin in this channel. Cannot delete messages.\n\n"
                                    "Please add your user account as an admin with 'Delete Messages' permission first.",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                    ])
                                )
                                return
                                
                            except UserAdminInvalidError:
                                # This means we're an admin but don't have the right permission
                                is_admin = True
                                has_delete_permission = False
                                admin_rights_checked = True
                                logger.info("Admin check failed: User is admin but lacks delete permissions")
                                
                                await status_msg.edit_text(
                                    "⚠️ Permission Error!\n\n"
                                    "Your admin account doesn't have 'Delete Messages' permission.\n\n"
                                    "Please update your permissions for this channel.",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                    ])
                                )
                                return
                            except Exception as test_error:
                                # Some other error with the test deletion
                                logger.error(f"Error during test deletion: {str(test_error)}")
                                # We'll fall back to the admin participant check
                                pass
                                
                    except Exception as get_msg_error:
                        logger.error(f"Error getting test message: {str(get_msg_error)}")
                    
                    # If we couldn't confirm through test deletion, try checking admin status through participant list
                    if not admin_rights_checked:
                        try:
                            # Get our own user info
                            me = await user_client.get_me()
                            my_id = me.id
                            
                            # Try to get admin participants list
                            participants = await user_client(GetParticipantsRequest(
                                channel=channel_entity,
                                filter=ChannelParticipantsAdmins(),
                                offset=0,
                                limit=100,
                                hash=0
                            ))
                                
                            # Check if we're in the admin list
                            for participant in participants.participants:
                                if hasattr(participant, 'user_id') and participant.user_id == my_id:
                                    is_admin = True
                                    # Check for delete messages permission if possible
                                    if hasattr(participant, 'admin_rights') and hasattr(participant.admin_rights, 'delete_messages'):
                                        has_delete_permission = participant.admin_rights.delete_messages
                                    else:
                                        # Assume we have permission if we can't check specifically
                                        has_delete_permission = True
                                    break
                            
                            if not is_admin:
                                await status_msg.edit_text(
                                    "⚠️ Permission Error!\n\n"
                                    "You are not an admin in this channel. Cannot delete messages.\n\n"
                                    "Please add your user account as an admin with 'Delete Messages' permission first.",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                    ])
                                )
                                return
                                
                            if not has_delete_permission:
                                await status_msg.edit_text(
                                    "⚠️ Permission Error!\n\n"
                                    "Your admin account doesn't have 'Delete Messages' permission.\n\n"
                                    "Please update your permissions for this channel.",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                    ])
                                )
                                return
                                
                        except Exception as admin_check_error:
                            logger.error(f"Error checking admin status: {str(admin_check_error)}")
                            # We failed to get a definitive answer - warn the user but try anyway
                            await status_msg.edit_text(
                                "⚠️ Warning: Could not verify admin status.\n\n"
                                "Attempting to delete messages anyway, but this may fail if you don't have admin permissions.\n\n"
                                "Proceeding in 3 seconds..."
                            )
                            await asyncio.sleep(3)
                    
                    # If we got here, either we know we can delete or we're attempting as a last resort
                    delete_success = False
                    try_message_count = 0
                    
                    # Start with a limited batch to confirm deletion is working
                    async for message in user_client.iter_messages(channel_entity, limit=500):
                        try_message_count += 1
                        try:
                            await user_client.delete_messages(channel_entity, message.id)
                            deleted_count += 1
                            delete_success = True
                            
                            # Update status every 10 messages
                            if deleted_count % 10 == 0:
                                try:
                                    await status_msg.edit_text(
                                        "🗑️ Channel purge in progress...\n\n"
                                        f"Deleting messages...\n"
                                        f"Deleted: {deleted_count} messages"
                                    )
                                except Exception as e:
                                    logger.error(f"Error updating status: {str(e)}")
                        except Exception as delete_error:
                            logger.error(f"Error deleting message {message.id}: {str(delete_error)}")
                            
                        # If we've tried 10 messages but none were deleted, exit the loop
                        if try_message_count >= 10 and deleted_count == 0:
                            # Display error message explaining the issue
                            await status_msg.edit_text(
                                "⚠️ Error: Unable to delete any messages.\n\n"
                                "Possible reasons:\n"
                                "• Not an admin in this channel\n"
                                "• Missing delete messages permission\n"
                                "• Channel is read-only or has restricted permissions\n\n"
                                "Please check your permissions and try again.",
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                    [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                ])
                            )
                            return
                    
                    # If purge and leave, post farewell sticker and leave the channel
                    if purge_and_leave:
                        sticker_success = False
                        try:
                            # Post farewell sticker
                            await status_msg.edit_text(
                                "🗑️ Purge completed. Posting farewell sticker..."
                            )
                            
                            # Try to send farewell stickers with multiple fallbacks
                            sticker_success = False
                            try:
                                import random
                                
                                # Check if we have stickers in our collection
                                if FAREWELL_STICKERS and len(FAREWELL_STICKERS) > 0:
                                    # Try up to 3 randomly selected stickers if we have enough
                                    sticker_attempts = min(3, len(FAREWELL_STICKERS))
                                    tried_stickers = set()
                                    
                                    for _ in range(sticker_attempts):
                                        # Get a sticker we haven't tried yet
                                        available_stickers = [s for s in FAREWELL_STICKERS if s not in tried_stickers]
                                        if not available_stickers:
                                            break
                                            
                                        sticker_id = random.choice(available_stickers)
                                        tried_stickers.add(sticker_id)
                                        
                                        try:
                                            # Try sending the sticker - explicitly as a sticker type
                                            await user_client.send_file(
                                                channel_entity,
                                                sticker_id,
                                                file_type='sticker'
                                            )
                                            sticker_success = True
                                            logger.info(f"Successfully sent farewell sticker: {sticker_id}")
                                            break  # Exit the loop if successful
                                        except Exception as e:
                                            logger.error(f"Failed to send sticker {sticker_id}: {str(e)}")
                                            # Continue trying other stickers
                                            continue
                                
                                # If all random stickers failed, try the default farewell sticker
                                if not sticker_success:
                                    try:
                                        await user_client.send_file(
                                            channel_entity, 
                                            FAREWELL_STICKER_ID,  # Use the constant directly
                                            file_type='sticker'
                                        )
                                        sticker_success = True
                                        logger.info("Sent default farewell sticker")
                                    except Exception as default_sticker_error:
                                        logger.error(f"Error sending default farewell sticker: {str(default_sticker_error)}")
                                
                            except Exception as sticker_error:
                                logger.error(f"Error in sticker sending process: {str(sticker_error)}")
                            
                            # If all sticker attempts failed, try to send a text message
                            if not sticker_success:
                                try:
                                    await user_client.send_message(
                                        channel_entity, 
                                        "👋 Goodbye! Channel cleanup completed."
                                    )
                                    logger.info("Sent text farewell message (fallback)")
                                    sticker_success = True  # We succeeded with the text message
                                except Exception as text_error:
                                    logger.error(f"Error sending farewell message: {str(text_error)}")
                            
                            # Leave the channel
                            await status_msg.edit_text(
                                "👋 Leaving channel..."
                            )
                            
                            # Small delay before leaving
                            await asyncio.sleep(1)
                            
                            # Leave the channel
                            await user_client.delete_dialog(channel_entity)
                            
                            # Final completion message
                            farewell_status = "Posted farewell message" if sticker_success else "Skipped farewell message (error)"
                            await status_msg.edit_text(
                                f"✅ Operation completed successfully!\n\n"
                                f"• Deleted {deleted_count} messages\n"
                                f"• {farewell_status}\n"
                                f"• Left the channel\n\n"
                                f"Return to menu to continue using the bot.",
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                    [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                ])
                            )
                        except Exception as leave_error:
                            logger.error(f"Error during leave process: {str(leave_error)}")
                            await status_msg.edit_text(
                                f"⚠️ Partial completion!\n\n"
                                f"• Successfully deleted {deleted_count} messages\n"
                                f"• Error during leave process: {str(leave_error)}\n\n"
                                f"You may need to manually leave the channel.",
                                reply_markup=InlineKeyboardMarkup([
                                    [InlineKeyboardButton("◀️ Back to Cleanup Menu", callback_data="channel_cleanup_menu")],
                                    [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                                ])
                            )
                    else:
                        # Regular purge completion message
                        await status_msg.edit_text(
                            f"✅ Channel purge completed!\n\n"
                            f"Successfully deleted {deleted_count} messages.\n\n"
                            f"Return to menu to continue using the bot.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("◀️ Back to Purge Menu", callback_data=return_callback)],
                                [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                            ])
                        )
                except Exception as e:
                    await status_msg.edit_text(
                        f"❌ Error during purge: {str(e)}\n\n"
                        f"Deleted {deleted_count} messages before error occurred.\n\n"
                        f"Possible reasons:\n"
                        f"• Bot lacks necessary permissions\n"
                        f"• Network or API errors\n"
                        f"• Rate limiting by Telegram",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("◀️ Back", callback_data=return_callback)],
                            [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                        ])
                    )
            except Exception as e:
                await query.edit_message_text(
                    f"❌ Error accessing channel: {str(e)}\n\n"
                    f"Possible reasons:\n"
                    f"• Bot is not an admin in the channel\n"
                    f"• Channel doesn't exist or was deleted\n"
                    f"• Bot lacks necessary permissions",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("◀️ Back", callback_data=return_callback)],
                        [InlineKeyboardButton("🏠 Back to Main Menu", callback_data="back_to_menu")]
                    ])
                )
        except ValueError:
            await query.edit_message_text(
                "Invalid channel ID format.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="channel_cleanup_menu")]])
            )

    elif query.data == "session_info":
        # Show session information
        session_info = "Session Information:\n\n"
        
        if not API_ID or not API_HASH:
            session_info += "❌ API credentials not configured\n"
        else:
            session_info += "✅ API credentials configured\n"
            
        if not USER_SESSION:
            session_info += "❌ User session not configured\n"
        else:
            session_info += "✅ User session configured\n\n"
            
            # Try to get user info if credentials are complete
            if API_ID and API_HASH and USER_SESSION and user_client:
                try:
                    # Make sure client is connected
                    if not user_client.is_connected():
                        await user_client.connect()
                    
                    if await user_client.is_user_authorized():
                        me = await user_client.get_me()
                        session_info += f"👤 Username: @{me.username or 'None'}\n"
                        session_info += f"📱 Phone: {me.phone or 'Unknown'}\n"
                        session_info += f"🆔 User ID: {me.id}\n"
                        session_info += f"\nThe client is using these credentials for reposting."
                    else:
                        session_info += "❌ Session is not authorized. Please generate a new session."
                except Exception as e:
                    session_info += f"❌ Error getting session info: {str(e)}"
            else:
                session_info += "❓ Unable to verify session authorization status."

        # Add session management buttons to the session info page
        session_buttons = []
        
        # Add session management options
        if USER_SESSION:
            session_buttons.append([
                InlineKeyboardButton("🗑️ Delete Session", callback_data="delete_session")
            ])
        
        session_buttons.append([
            InlineKeyboardButton("➕ Add New Session", callback_data="add_session")
        ])
        
        # Add back button
        session_buttons.append([
            InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")
        ])
        
        await query.edit_message_text(
            session_info,
            reply_markup=InlineKeyboardMarkup(session_buttons)
        )
        
    elif query.data == "auto_add_tags":
        # Auto-add common tag formats for the destination channel
        destination_tag = None
        dest_username = None
        if active_channels["destination"]:
            try:
                dest_info = await get_entity_info(user_client, active_channels["destination"])
                if dest_info and dest_info.get("username"):
                    destination_tag = f"@{dest_info['username']}"
                    dest_username = dest_info.get("username")
            except Exception as e:
                logger.error(f"Error getting destination tag: {str(e)}")
        
        if not destination_tag:
            await query.edit_message_text(
                "Cannot auto-add tags. Destination channel has no username.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Tags", callback_data="manage_tags")]])
            )
            return
        
        # Get common source channel usernames to create tag replacements for
        source_usernames = []
        for channel_id in active_channels["source"]:
            try:
                info = await get_entity_info(user_client, channel_id)
                if info and info.get("username"):
                    source_usernames.append(info.get("username"))
            except Exception as e:
                logger.error(f"Error getting source channel info: {str(e)}")
        
        tags_added = 0
        
        # For each source channel with a username, create common format replacements
        for username in source_usernames:
            # @username format
            source_tag = f"@{username}"
            if source_tag != destination_tag and source_tag not in tag_replacements:
                tag_replacements[source_tag] = destination_tag
                tags_added += 1
            
            # t.me/username format
            source_tme = f"t.me/{username}"
            dest_tme = f"t.me/{dest_username}"
            if source_tme != dest_tme and source_tme not in tag_replacements:
                tag_replacements[source_tme] = dest_tme
                tags_added += 1
            
            # https://t.me/username format
            source_https = f"https://t.me/{username}"
            dest_https = f"https://t.me/{dest_username}"
            if source_https != dest_https and source_https not in tag_replacements:
                tag_replacements[source_https] = dest_https
                tags_added += 1
        
        # Save the new tag replacements
        if tags_added > 0:
            await save_tag_config()
            await query.edit_message_text(
                f"✅ Added {tags_added} tag replacements automatically.\n\n"
                f"The bot will now replace mentions and links from source channels with {destination_tag}.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Tags", callback_data="manage_tags")]])
            )
        else:
            await query.edit_message_text(
                "No new tag replacements were added. All necessary replacements may already exist.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Tags", callback_data="manage_tags")]])
            )
    
    elif query.data == "manage_admins":
        # Show admin management menu with improved UI
        
        # Create grouped action buttons
        action_buttons = [
            [
                InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
                InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")
            ]
        ]
        
        # Back button
        back_button = [[InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_menu")]]
        
        # Combine all button sections
        keyboard = []
        keyboard.extend(action_buttons)
        keyboard.extend(back_button)
        
        # Format the admin list nicely
        admin_list = []
        for admin_id in ADMIN_USERS:
            # Mark original admin with a crown emoji
            if admin_id == 7325746010:
                admin_list.append(f"👑 {admin_id} (original)")
            else:
                admin_list.append(f"👤 {admin_id}")
        
        admin_text = "\n".join(admin_list)
        
        await query.edit_message_text(
            f"👥 Admin Management\n\n"
            f"Admins can control this bot and configure channel settings.\n\n"
            f"Current admins:\n{admin_text}\n\n"
            f"Use the buttons below to manage admins:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "add_admin":
        # Admin addition process
        await query.edit_message_text(
            "Please enter the Telegram User ID of the admin to add.\n\n"
            "Note: The user must first send a message to this bot or start a conversation with it.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
        )
        context.user_data["awaiting"] = "admin_id"
    
    elif query.data == "remove_admin":
        # Show list of admins to remove
        if len(ADMIN_USERS) <= 1:
            await query.edit_message_text(
                "Cannot remove the last admin. There must always be at least one admin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
            return
        
        keyboard = []
        for admin_id in ADMIN_USERS:
            if admin_id != 7325746010:  # Don't allow removing the original admin
                keyboard.append([InlineKeyboardButton(f"Remove: {admin_id}", callback_data=f"remove_admin_{admin_id}")])
        
        keyboard.append([InlineKeyboardButton("Back", callback_data="manage_admins")])
        
        await query.edit_message_text(
            "Select an admin to remove:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith("remove_admin_"):
        # Handle admin removal
        admin_id = int(query.data.split("_")[2])
        if admin_id in ADMIN_USERS and len(ADMIN_USERS) > 1:
            ADMIN_USERS.remove(admin_id)
            await save_admin_config()
            
            # Show updated admin list
            admin_text = "\n".join([f"• {admin_id}" for admin_id in ADMIN_USERS])
            
            await query.edit_message_text(
                f"Admin removed successfully.\n\n"
                f"Current admins:\n{admin_text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
        else:
            await query.edit_message_text(
                "Cannot remove this admin. Either the admin doesn't exist or it's the last admin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
    
    elif query.data.startswith("confirm_add_admin_"):
        # Confirm adding a new admin
        new_admin_id = int(query.data.split("_")[3])
        if new_admin_id not in ADMIN_USERS:
            ADMIN_USERS.append(new_admin_id)
            await save_admin_config()
            
            # Show updated admin list
            admin_text = "\n".join([f"• {admin_id}" for admin_id in ADMIN_USERS])
            
            await query.edit_message_text(
                f"Admin added successfully.\n\n"
                f"Current admins:\n{admin_text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
        else:
            await query.edit_message_text(
                "This user is already an admin.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
    
    elif query.data == "config_api":
        # Show API configuration options with improved UI
        
        # Grouped credentials buttons
        api_buttons = [
            [InlineKeyboardButton("🔢 Set API_ID", callback_data="set_api_id")],
            [InlineKeyboardButton("🔑 Set API_HASH", callback_data="set_api_hash")],
            [InlineKeyboardButton("🔐 Set USER_SESSION", callback_data="set_user_session")],
            [
                InlineKeyboardButton("🗑️ Delete Session", callback_data="delete_session"),
                InlineKeyboardButton("➕ Add Session", callback_data="add_session")
            ]
        ]
        
        # Back button
        back_button = [[InlineKeyboardButton("◀️ Back to Main Menu", callback_data="back_to_menu")]]
        
        # Combine button sections
        keyboard = []
        keyboard.extend(api_buttons)
        keyboard.extend(back_button)
        
        # Get current configuration status with emoji indicators
        api_id_status = "✅ Configured" if API_ID else "❌ Not configured"
        api_hash_status = "✅ Configured" if API_HASH else "❌ Not configured"
        user_session_status = "✅ Configured" if USER_SESSION else "❌ Not configured"
        
        # Check overall status
        all_configured = API_ID and API_HASH and USER_SESSION
        overall_status = "✅ All credentials configured" if all_configured else "⚠️ Missing credentials"
        
        await query.edit_message_text(
            "🔑 API Configuration\n\n"
            f"Status: {overall_status}\n\n"
            f"API_ID: {api_id_status}\n"
            f"API_HASH: {api_hash_status}\n"
            f"USER_SESSION: {user_session_status}\n\n"
            "These credentials are required for the bot to access Telegram channels.\n\n"
            "📋 How to obtain credentials:\n"
            "1. Get API_ID and API_HASH from https://my.telegram.org/apps\n"
            "2. Generate USER_SESSION by running the gen_session.py script\n\n"
            "Select an option to configure:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "set_api_id":
        await query.edit_message_text(
            "Please enter your Telegram API ID.\n\n"
            "You can obtain this from https://my.telegram.org/apps",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="config_api")]])
        )
        context.user_data["awaiting"] = "api_id"
    
    elif query.data == "set_api_hash":
        await query.edit_message_text(
            "Please enter your Telegram API Hash.\n\n"
            "You can obtain this from https://my.telegram.org/apps",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="config_api")]])
        )
        context.user_data["awaiting"] = "api_hash"
    
    elif query.data == "set_user_session":
        await query.edit_message_text(
            "🔐 Set User Session\n\n"
            "Please enter your USER_SESSION string. This is a long string that looks like a random sequence of characters.\n\n"
            "ℹ️ You can generate this by running:\n"
            "  `python run.py session`\n\n"
            "⚠️ After generating the session, copy the ENTIRE string (it's very long!) and paste it here as a message.\n\n"
            "💡 Tip: Session strings usually start with `1A` or similar and contain many characters.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Cancel", callback_data="config_api")]])
        )
        context.user_data["awaiting"] = "user_session"
    
    elif query.data == "back_to_menu":
        # Since we can't edit a text message to include an image, and we can't edit an image message to include buttons,
        # we'll delete the current message and send two new ones: an image followed by the menu text with buttons

        # Check if API credentials and session are available
        missing_credentials = False
        if not API_ID or not API_HASH or not USER_SESSION:
            missing_credentials = True
        
        # Group buttons by functionality for better organization
        
        # Channel configuration section
        channel_buttons = [
            [
                InlineKeyboardButton("➕ Add Source", callback_data="add_source"),
                InlineKeyboardButton("➖ Remove Source", callback_data="remove_source")
            ],
            [
                InlineKeyboardButton("🎯 Set Destination", callback_data="set_destination"),
                InlineKeyboardButton("🗑️ Remove Destination", callback_data="remove_destination")
            ],
            [
                InlineKeyboardButton("⚙️ Channel Management", callback_data="channel_settings_menu")
            ]
        ]
        
        # Controls section - operation buttons
        control_buttons = [
            [
                InlineKeyboardButton("▶️ Start Reposting", callback_data="start_reposting"),
                InlineKeyboardButton("⏹️ Stop Reposting", callback_data="stop_reposting")
            ]
        ]
        
        # Settings section
        settings_buttons = [
            [InlineKeyboardButton("🏷️ Manage Tags", callback_data="manage_tags")],
            [InlineKeyboardButton("🚩 Content Filters", callback_data="content_filters")],
            [InlineKeyboardButton("👥 Manage Admins", callback_data="manage_admins")],
            [InlineKeyboardButton("ℹ️ View Config", callback_data="view_config")],
            [InlineKeyboardButton("🧹 Toggle Clean Mode", callback_data="toggle_clean_mode")],
            [InlineKeyboardButton(f"🗑️ Deletion Sync Settings", callback_data="deletion_sync")]
        ]
        
        # Add API credentials section if missing
        if missing_credentials:
            settings_buttons.insert(0, [InlineKeyboardButton("🔑 Configure API Credentials", callback_data="config_api")])
        
        # Information section
        info_buttons = [
            [InlineKeyboardButton("📊 Session Info", callback_data="session_info")]
        ]
        
        # Combine all sections into the keyboard
        keyboard = []
        keyboard.extend(channel_buttons)
        keyboard.extend(control_buttons)
        keyboard.extend(settings_buttons)
        keyboard.extend(info_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Prepare welcome text
        welcome_text = "Welcome to the Channel Reposter Bot!\n\n" \
                      "This bot reposts content from source channels to a destination channel " \
                      "without the forward tag, and can replace channel tags with custom values.\n\n"
        
        if missing_credentials:
            welcome_text += "⚠️ API credentials are missing. You need to configure them to use full reposting functionality.\n\n"
        
        welcome_text += "Use the buttons below to configure and control the bot."
        
        # Delete previous menu messages if they exist
        user_id = query.from_user.id  # Use query.from_user instead of update.effective_user
        chat_id = query.message.chat_id
        
        # Delete the current message with multi-step approach for maximum reliability
        try:
            # First attempt simple deletion
            await query.message.delete()
            logger.info(f"Successfully deleted menu message {query.message.message_id}")
        except Exception as e:
            logger.error(f"Standard deletion failed: {str(e)}")
            
            # Try a two-phase deletion - first edit, then delete
            try:
                # If it's a photo, edit the caption first
                if hasattr(query.message, 'photo') and query.message.photo:
                    await query.message.edit_caption(caption=".")
                else:
                    # Otherwise edit the text
                    await query.message.edit_text(text=".")
                    
                # Now try deletion again
                await query.message.delete()
                logger.info("Two-phase deletion succeeded")
            except Exception as edit_error:
                logger.error(f"Two-phase deletion also failed: {str(edit_error)}")
                
        # Create and delete a temporary message to disrupt button display
        try:
            temp_msg = await context.bot.send_message(
                chat_id=chat_id,
                text="Refreshing menu..."
            )
            await temp_msg.delete()
            logger.info("Created and deleted temporary message")
        except Exception as temp_error:
            logger.error(f"Failed to create/delete temporary message: {str(temp_error)}")
        
        # Collect all messages to delete from both global tracking and context
        message_ids = []
        
        # Check global tracking first
        if user_id in user_message_history and chat_id in user_message_history[user_id]:
            message_ids.extend(user_message_history[user_id][chat_id])
            logger.info(f"Found {len(user_message_history[user_id][chat_id])} messages in global tracking")
        
        # Also check context for backward compatibility
        if "message_ids" in context.user_data:
            message_ids.extend(context.user_data["message_ids"])
            logger.info(f"Found {len(context.user_data['message_ids'])} messages in user_data")
        
        # Delete all stored messages
        for msg_id in message_ids:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.info(f"Deleted stored message {msg_id}")
            except Exception as e:
                logger.error(f"Error deleting stored message {msg_id}: {str(e)}")
        
        # Initialize or reset the message tracking
        context.user_data["message_ids"] = []
        
        # Initialize the user's entry in the global tracking if needed
        if user_id not in user_message_history:
            user_message_history[user_id] = {}
        
        # Clear the existing messages for this chat
        user_message_history[user_id][chat_id] = []
        
        # Send new image and store its ID
        try:
            img_message = await query.message.chat.send_photo(
                photo=open("assets/menu_image.jpeg", "rb"),
                caption="Channel Reposter Bot"
            )
            # Store in context for backward compatibility
            context.user_data["message_ids"].append(img_message.message_id)
            # Store in global tracking
            user_message_history[user_id][chat_id].append(img_message.message_id)
            logger.info(f"Stored image message ID: {img_message.message_id}")
        except Exception as e:
            logger.error(f"Error sending image in back_to_menu: {str(e)}")
        
        # Send new menu with buttons and store its ID
        try:
            menu_message = await query.message.chat.send_message(
                text=welcome_text,
                reply_markup=reply_markup
            )
            # Store in context for backward compatibility
            context.user_data["message_ids"].append(menu_message.message_id)
            # Store in global tracking
            user_message_history[user_id][chat_id].append(menu_message.message_id)
            logger.info(f"Stored menu message ID: {menu_message.message_id}")
        except Exception as e:
            logger.error(f"Error sending menu in back_to_menu: {str(e)}")
            # Final fallback - at least try to send a simple text menu without tracking
            try:
                fallback_msg = await query.message.chat.send_message(
                    text="Channel Reposter Bot Menu\n\nUse the buttons below to configure and control the bot.",
                    reply_markup=reply_markup
                )
                # Try to store this fallback message ID
                try:
                    context.user_data["message_ids"].append(fallback_msg.message_id)
                    user_message_history[user_id][chat_id].append(fallback_msg.message_id)
                except Exception as track_error:
                    logger.error(f"Error tracking fallback message: {str(track_error)}")
            except Exception as final_error:
                logger.error(f"Final fallback failed in back_to_menu: {str(final_error)}")

async def handle_sticker_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle sticker input for the bot"""
    global farewell_sticker_id, BOT_CONFIG, channel_settings
    
    # Log that we received a sticker - MAKE THIS SUPER OBVIOUS IN LOGS
    print("========================================")
    print("🎭🎭🎭 STICKER HANDLER ACTIVATED 🎭🎭🎭")
    print("========================================")
    logger.info("STICKER HANDLER: Received a sticker message")
    
    # Ignore messages that aren't from admin users
    user_id = update.effective_user.id
    if user_id not in ADMIN_USERS:
        logger.info("STICKER HANDLER: User not in admin list, rejecting")
        await update.message.reply_text("You are not authorized to use this bot.🥹")
        return
    
    # Get sticker ID
    sticker = update.message.sticker
    sticker_id = sticker.file_id
    
    logger.info(f"Received sticker with ID: {sticker_id}")
    
    # Instead of processing directly, just show the instructions for using the standalone script
    add_mode = ""
    replace_mode = ""
    
    # If we were in a specific context, provide a more tailored message
    if "awaiting" in context.user_data and context.user_data["awaiting"] == "farewell_sticker_input":
        if context.user_data.get("sticker_mode", "add") == "add":
            add_mode = " (RECOMMENDED for your current action)"
        else:
            replace_mode = " (RECOMMENDED for your current action)"
        
        # Clear awaiting state since we're not processing it directly
        context.user_data.pop("awaiting", None)
    
    # First, confirm by sending the sticker back to the user, so they can see what they selected
    try:
        await update.message.reply_sticker(sticker_id)
    except Exception as e:
        logger.error(f"Error sending sticker preview: {e}")
    
    # Send instructions for the standalone script
    instructions = (
        f"📋 **Sticker ID Received**\n\n"
        f"`{sticker_id}`\n\n"
        f"Due to technical issues with direct sticker handling, please use the standalone script method instead:\n\n"
        f"**Option 1: Add to Collection{add_mode}**\n"
        f"```\n"
        f"python set_farewell_sticker_input.py \"{sticker_id}\" add\n"
        f"```\n\n"
        f"**Option 2: Replace All Stickers{replace_mode}**\n"
        f"```\n"
        f"python set_farewell_sticker_input.py \"{sticker_id}\" replace\n"
        f"```\n\n"
        f"Run one of these commands in your Replit terminal to set the sticker."
    )
    
    await update.message.reply_text(
        instructions,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 View Settings", callback_data="view_channel_settings")],
            [InlineKeyboardButton("⚙️ Back to Settings", callback_data="channel_settings_menu")]
        ])
    )


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for configuration settings"""
    user_id = update.effective_user.id
    message_text = update.message.text.strip()
    
    # Special handling for session string direct input - check if it looks like a session string
    if len(message_text) > 100 and message_text.startswith("1"):
        # This could be a session string being pasted, let's process it
        logger.info("Detected possible session string direct input")
        
        # Set up the awaiting state to process as user_session
        context.user_data["awaiting"] = "user_session"
        
        # Log the detection to help with debugging
        logger.info(f"Setting up to process direct session input (length: {len(message_text)})")
    
    # Allow the user to continue if they're adding themself as admin, configuring API, or awaiting admin_id
    if ("awaiting" in context.user_data and 
        (context.user_data["awaiting"] == "admin_id" or
         context.user_data["awaiting"] in ["api_id", "api_hash", "user_session"])):
        pass
    elif user_id not in ADMIN_USERS:
        await update.message.reply_text("You are not authorized to use this bot.🥹")
        return
    
    if "awaiting" not in context.user_data:
        await update.message.reply_text("I'm not expecting any input. Use /start to access the menu.")
        return
    
    awaiting = context.user_data["awaiting"]
    
    # Handle API credentials input
    if awaiting == "api_id":
        api_id_input = update.message.text.strip()
        try:
            # Validate it's a number
            new_api_id = int(api_id_input)
            
            # Update API_ID in environment (for current session)
            global API_ID
            API_ID = new_api_id
            os.environ["API_ID"] = str(new_api_id)
            
            # Save to config directly (no need to update .env file)
            try:
                with open(".env", "a+") as f:
                    f.seek(0)
                    content = f.read()
                    if "API_ID=" not in content:
                        f.write(f"\nAPI_ID={str(new_api_id)}\n")
            except Exception as e:
                logger.error(f"Error saving API_ID: {str(e)}")
            
            await update.message.reply_text(
                "API ID has been set successfully!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
            )
        except ValueError:
            await update.message.reply_text(
                "Invalid API ID format. Please enter a valid numeric API ID.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data="set_api_id")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "api_hash":
        api_hash_input = update.message.text.strip()
        
        # API hash is typically a 32-character hexadecimal string
        if len(api_hash_input) == 32 and all(c in "0123456789abcdef" for c in api_hash_input.lower()):
            # Update API_HASH in environment (for current session)
            global API_HASH
            API_HASH = api_hash_input
            os.environ["API_HASH"] = api_hash_input
            
            # Save to config directly
            try:
                with open(".env", "a+") as f:
                    f.seek(0)
                    content = f.read()
                    if "API_HASH=" not in content:
                        f.write(f"\nAPI_HASH={api_hash_input}\n")
            except Exception as e:
                logger.error(f"Error saving API_HASH: {str(e)}")
            
            await update.message.reply_text(
                "API Hash has been set successfully!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
            )
        else:
            await update.message.reply_text(
                "Invalid API Hash format. A valid API hash is typically a 32-character hexadecimal string.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data="set_api_hash")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "user_session":
        user_session_input = update.message.text.strip()
        
        # Session strings are long, so just do basic validation
        if len(user_session_input) > 20:  # Just checking it's not empty or too short
            # Update USER_SESSION in environment (for current session)
            global USER_SESSION
            USER_SESSION = user_session_input
            os.environ["USER_SESSION"] = user_session_input
            
            # Save to .env file properly
            try:
                # Check if .env file exists
                if os.path.exists(".env"):
                    # Read current content
                    with open(".env", "r") as f:
                        content = f.read()
                    
                    # Check if USER_SESSION already exists in the file
                    if "USER_SESSION=" in content:
                        # Replace the existing session string
                        content = re.sub(
                            r'USER_SESSION=.*(\n|$)',
                            f'USER_SESSION={user_session_input}\n',
                            content
                        )
                    else:
                        # Add the session string if it doesn't exist
                        content += f'\nUSER_SESSION={user_session_input}\n'
                    
                    # Write the updated content back to the file
                    with open(".env", "w") as f:
                        f.write(content)
                else:
                    # Create a new .env file if it doesn't exist
                    with open(".env", "w") as f:
                        f.write(f'USER_SESSION={user_session_input}\n')
                        
                logger.info("Successfully saved USER_SESSION to .env file")
            except Exception as e:
                logger.error(f"Error saving USER_SESSION to .env file: {str(e)}")
            
            # Try to initialize the client with the new session
            try:
                global user_client
                # Create new user client with updated session
                if API_ID and API_HASH:
                    user_client = TelegramClient(
                        StringSession(USER_SESSION),
                        API_ID,
                        API_HASH
                    )
                    
                    # Try to get session owner information
                    try:
                        # Start the client to get user info
                        await user_client.connect()
                        
                        if await user_client.is_user_authorized():
                            me = await user_client.get_me()
                            success_message = f"✅ Session loaded successfully!\n\n👤 Username: @{me.username or 'None'}\n📱 Phone: {me.phone or 'Unknown'}\n🆔 User ID: {me.id}\n\nThe client will use these credentials for reposting."
                        else:
                            success_message = "Session has been saved, but it's not authorized. You may need to generate a new session."
                        
                        # Disconnect after getting info (will reconnect later as needed)
                        await user_client.disconnect()
                    except Exception as e:
                        logger.error(f"Error getting session owner info: {str(e)}")
                        success_message = "User session has been set successfully! Client will use these credentials next time."
                else:
                    success_message = "User session has been saved, but API ID and Hash are still needed to connect."
            except Exception as e:
                logger.error(f"Error setting up client with new session: {str(e)}")
                success_message = f"User session has been saved, but there was an error setting up the client: {str(e)}"
            
            await update.message.reply_text(
                success_message,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to API Config", callback_data="config_api")]])
            )
        else:
            await update.message.reply_text(
                "Invalid session string. The session string should be a long string of characters.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Try Again", callback_data="set_user_session")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    if awaiting == "source_channel":
        # Handle source channel input
        channel_input = update.message.text.strip()
        
        # Check if client is available
        if not user_client:
            await update.message.reply_text(
                "❌ API credentials are not configured. Please configure API_ID, API_HASH, and USER_SESSION first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Configure API", callback_data="config_api")]])
            )
            # Clear awaiting state
            context.user_data.pop("awaiting", None)
            return
            
        # Make sure the client is connected
        if not user_client.is_connected():
            try:
                logger.info("Client not connected. Attempting to connect...")
                await user_client.connect()
                if not user_client.is_connected():
                    await update.message.reply_text(
                        "❌ Cannot connect to Telegram servers. Please check your API credentials and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                await update.message.reply_text(
                    f"❌ Connection error: {str(e)}. Please check your internet connection and API credentials.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
        
        try:
                        # Handle different channel input formats
            channel_id = None
            
            try:
                # Simplified format handling that's more reliable
                # First, check if it's a Telegram link
                if "t.me/" in channel_input or "telegram.me/" in channel_input:
                    logger.info(f"Processing Telegram link: {channel_input}")
                    # Extract username from link
                    username_part = channel_input.split("/")[-1]
                    logger.info(f"Extracted username from link: {username_part}")
                    
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(username_part)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from link: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from link: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel from link: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Then, check if it's a username format
                elif channel_input.startswith('@'):
                    logger.info(f"Processing username: {channel_input}")
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(channel_input)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from username: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from username: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Finally, try to convert to int (for direct channel IDs)
                else:
                    try:
                        channel_id = int(channel_input)
                        logger.info(f"Using direct channel ID: {channel_id}")
                    except ValueError:
                        logger.error(f"Invalid channel format: {channel_input}")
                        await update.message.reply_text(
                            "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                            "a username (@channel), or a t.me link.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
            except Exception as e:
                logger.error(f"Unexpected error processing channel format: {str(e)}")
                await update.message.reply_text(
                    f"❌ Error processing channel format: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
# Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "Could not verify this channel. Please check the ID or username and try again."
                    )
                    return
                
                # Try to join the channel if needed
                await join_channel(user_client, channel_id)
                
                # Add to source channels if not already present
                if channel_id not in active_channels["source"]:
                    active_channels["source"].append(channel_id)
                    await save_config()
                    await update.message.reply_text(
                        f"Added {info.get('title', channel_id)} to source channels.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                    )
                else:
                    await update.message.reply_text(
                        "This channel is already in your source list.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                    )
            except Exception as e:
                await update.message.reply_text(
                    f"Error adding channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                )
        except ValueError:
            await update.message.reply_text(
                "Invalid channel format. Please use a numeric ID or @username.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "destination_channel":
        # Handle destination channel input
        channel_input = update.message.text.strip()
        
        # Check if client is available
        if not user_client:
            await update.message.reply_text(
                "API credentials are not configured. Please configure API_ID, API_HASH, and USER_SESSION first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Configure API", callback_data="config_api")]])
            )
            # Clear awaiting state
            context.user_data.pop("awaiting", None)
            return
            
        try:
                        # Handle different channel input formats
            channel_id = None
            
            try:
                # Simplified format handling that's more reliable
                # First, check if it's a Telegram link
                if "t.me/" in channel_input or "telegram.me/" in channel_input:
                    logger.info(f"Processing Telegram link: {channel_input}")
                    # Extract username from link
                    username_part = channel_input.split("/")[-1]
                    logger.info(f"Extracted username from link: {username_part}")
                    
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(username_part)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from link: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from link: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel from link: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Then, check if it's a username format
                elif channel_input.startswith('@'):
                    logger.info(f"Processing username: {channel_input}")
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(channel_input)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from username: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from username: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Finally, try to convert to int (for direct channel IDs)
                else:
                    try:
                        channel_id = int(channel_input)
                        logger.info(f"Using direct channel ID: {channel_id}")
                    except ValueError:
                        logger.error(f"Invalid channel format: {channel_input}")
                        await update.message.reply_text(
                            "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                            "a username (@channel), or a t.me link.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
            except Exception as e:
                logger.error(f"Unexpected error processing channel format: {str(e)}")
                await update.message.reply_text(
                    f"❌ Error processing channel format: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
# Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "Could not verify this channel. Please check the ID or username and try again."
                    )
                    return
                
                # Try to join the channel if needed
                await join_channel(user_client, channel_id)
                
                # Set as destination channel
                active_channels["destination"] = channel_id
                await save_config()
                await update.message.reply_text(
                    f"Set {info.get('title', channel_id)} as the destination channel.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                )
            except Exception as e:
                await update.message.reply_text(
                    f"Error setting destination channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                )
        except ValueError:
            await update.message.reply_text(
                "Invalid channel format. Please use a numeric ID or @username.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "tag_replacement":
        # Handle tag replacement input
        tag_input = update.message.text.strip()
        
        # Parse the input (format: old_tag → new_tag)
        if "→" in tag_input:
            old_tag, new_tag = tag_input.split("→", 1)
            old_tag = old_tag.strip()
            new_tag = new_tag.strip()
            
            # Validate tags (they should be @username or t.me/username format)
            valid_tag = False
            if (old_tag.startswith('@') and new_tag.startswith('@')) or \
               (old_tag.startswith('t.me/') and new_tag.startswith('t.me/')):
                valid_tag = True
            
            if valid_tag:
                # Add to tag replacements
                tag_replacements[old_tag] = new_tag
                await save_tag_config()
                await update.message.reply_text(
                    f"Added tag replacement: {old_tag} → {new_tag}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                )
            else:
                await update.message.reply_text(
                    "Invalid tag format. Both tags should be in the same format (@username or t.me/username).",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
                )
        else:
            await update.message.reply_text(
                "Invalid format. Please use the format: old_tag → new_tag",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
        
    elif awaiting == "destination_channel_add":
        # Handle destination channel add input
        channel_input = update.message.text.strip()
        
        # Check if client is available
        if not user_client:
            await update.message.reply_text(
                "❌ API credentials are not configured. Please configure API_ID, API_HASH, and USER_SESSION first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Configure API", callback_data="config_api")]])
            )
            # Clear awaiting state
            context.user_data.pop("awaiting", None)
            return
            
        try:
            # Handle different channel input formats
            channel_id = None
            
            try:
                # Simplified format handling that's more reliable
                # First, check if it's a Telegram link
                if "t.me/" in channel_input or "telegram.me/" in channel_input:
                    logger.info(f"Processing Telegram link: {channel_input}")
                    # Extract username from link
                    username_part = channel_input.split("/")[-1]
                    logger.info(f"Extracted username from link: {username_part}")
                    
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(username_part)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from link: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from link: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel from link: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Then, check if it's a username format
                elif channel_input.startswith('@'):
                    logger.info(f"Processing username: {channel_input}")
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(channel_input)
                        channel_id = entity.id
                        logger.info(f"Resolved channel ID from username: {channel_id}")
                    except Exception as e:
                        logger.error(f"Error resolving channel from username: {str(e)}")
                        await update.message.reply_text(
                            f"❌ Error resolving channel: {str(e)}\n\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                
                # Finally, try to convert to int (for direct channel IDs)
                else:
                    try:
                        channel_id = int(channel_input)
                        logger.info(f"Using direct channel ID: {channel_id}")
                    except ValueError:
                        logger.error(f"Invalid channel format: {channel_input}")
                        await update.message.reply_text(
                            "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                            "a username (@channel), or a t.me link.",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
            except Exception as e:
                logger.error(f"Unexpected error processing channel format: {str(e)}")
                await update.message.reply_text(
                    f"❌ Error processing channel format: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                )
                context.user_data.pop("awaiting", None)
                return
            
            # Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "❌ Could not verify this channel. Please check the ID or username and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
                
                # Try to join the channel if needed
                await join_channel(user_client, channel_id)
                
                # Add to destination channels list if not already present
                if channel_id not in active_channels["destinations"]:
                    active_channels["destinations"].append(channel_id)
                    await save_config()
                    await update.message.reply_text(
                        f"✅ Added {info.get('title', channel_id)} to destination channels.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Destinations", callback_data="manage_destinations")]])
                    )
                else:
                    await update.message.reply_text(
                        "ℹ️ This channel is already in your destinations list.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Destinations", callback_data="manage_destinations")]])
                    )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error adding destination channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
                )
        except ValueError:
            await update.message.reply_text(
                "❌ Invalid channel format. Please use a numeric ID or @username.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="manage_destinations")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "admin_id":
        # Handle admin ID input
        admin_input = update.message.text.strip()
        
        try:
            # Try to convert the input to an integer (Telegram user ID)
            new_admin_id = int(admin_input)
            
            # Confirm adding this admin
            keyboard = [
                [InlineKeyboardButton("Yes, add this admin", callback_data=f"confirm_add_admin_{new_admin_id}")],
                [InlineKeyboardButton("No, cancel", callback_data="manage_admins")]
            ]
            
            await update.message.reply_text(
                f"Do you want to add user ID {new_admin_id} as an admin?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except ValueError:
            await update.message.reply_text(
                "Invalid user ID format. Please enter a numeric Telegram user ID.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="manage_admins")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "farewell_sticker_input":
        # Process direct sticker ID input
        sticker_id = update.message.text.strip()
        
        # Very basic validation: check if it looks like a Telegram sticker ID
        if sticker_id.startswith("CAA") or sticker_id.startswith("CAB") or sticker_id.startswith("CAC"):
            # Update the farewell sticker ID
            global farewell_sticker_id, BOT_CONFIG, channel_settings
            channel_settings["farewell_sticker_id"] = sticker_id
            farewell_sticker_id = sticker_id
            
            # Save the setting to BOT_CONFIG
            BOT_CONFIG["farewell_sticker_id"] = sticker_id
            save_bot_config()
            
            # Save the sticker ID to constants.py for permanent storage
            try:
                constants_saved = await update_farewell_sticker_constant(sticker_id)
                logger.info(f"Updated farewell sticker constant: {constants_saved}")
            except Exception as e:
                logger.error(f"Error updating farewell sticker constant: {e}")
                constants_saved = False
            
            # First, try to send the sticker preview
            try:
                await update.message.reply_sticker(sticker_id)
            except Exception as e:
                logger.error(f"Error sending sticker preview: {e}")
            
            # Then confirm the update
            success_text = f"✅ Farewell sticker ID updated successfully!\n\n"
            if constants_saved:
                success_text += f"This sticker has been permanently saved and will be used for all farewell messages."
            else:
                success_text += f"This sticker will be sent before leaving a channel."
            
            # Confirm the change
            await update.message.reply_text(
                success_text,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 View Settings", callback_data="view_channel_settings")],
                    [InlineKeyboardButton("⚙️ Back to Settings", callback_data="channel_settings_menu")]
                ])
            )
        else:
            # Invalid sticker ID format
            await update.message.reply_text(
                "❌ Invalid sticker ID format. Sticker IDs typically start with 'CAA', 'CAB', or 'CAC'.\n\n"
                "Please *send a sticker directly* by tapping the sticker icon in your keyboard.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("◀️ Cancel", callback_data="channel_settings_menu")]
                ])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
    
    elif awaiting == "purge_channel_input":
        # Handle purge channel input
        channel_input = update.message.text.strip()
        
        # Check if client is available
        if not user_client:
            await update.message.reply_text(
                "❌ API credentials are not configured. Please configure API_ID, API_HASH, and USER_SESSION first.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⚙️ Configure API", callback_data="config_api")]])
            )
            # Clear awaiting state
            context.user_data.pop("awaiting", None)
            return
            
        # Make sure the client is connected
        if not user_client.is_connected():
            try:
                logger.info("Client not connected. Attempting to connect...")
                await user_client.connect()
                if not user_client.is_connected():
                    await update.message.reply_text(
                        "❌ Cannot connect to Telegram servers. Please check your API credentials and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="channel_settings_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            except Exception as e:
                logger.error(f"Connection error: {str(e)}")
                await update.message.reply_text(
                    f"❌ Connection error: {str(e)}. Please check your internet connection and API credentials.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="channel_settings_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
        
        try:
            # Normalize the channel input
            channel_id = None
            
            # First, check if it's a Telegram link
            if "t.me/" in channel_input or "telegram.me/" in channel_input:
                logger.info(f"Processing Telegram link: {channel_input}")
                # Extract username from link
                username_part = channel_input.split("/")[-1]
                logger.info(f"Extracted username from link: {username_part}")
                
                try:
                    # Try to resolve the username to an ID
                    entity = await user_client.get_entity(username_part)
                    channel_id = entity.id
                    logger.info(f"Resolved channel ID from link: {channel_id}")
                except Exception as e:
                    logger.error(f"Error resolving channel from link: {str(e)}")
                    await update.message.reply_text(
                        f"❌ Error resolving channel from link: {str(e)}\n\n"
                        f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Then, check if it's a username format
            elif channel_input.startswith('@'):
                logger.info(f"Processing username: {channel_input}")
                try:
                    # Try to resolve the username to an ID
                    entity = await user_client.get_entity(channel_input)
                    channel_id = entity.id
                    logger.info(f"Resolved channel ID from username: {channel_id}")
                except Exception as e:
                    logger.error(f"Error resolving channel from username: {str(e)}")
                    await update.message.reply_text(
                        f"❌ Error resolving channel: {str(e)}\n\n"
                        f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Finally, try to convert to int (for direct channel IDs)
            else:
                try:
                    channel_id = int(channel_input)
                    logger.info(f"Using direct channel ID: {channel_id}")
                except ValueError:
                    logger.error(f"Invalid channel format: {channel_input}")
                    await update.message.reply_text(
                        "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                        "a username (@channel), or a t.me link.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Verify the channel exists and we can access it
            try:
                # Try to get channel information
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "❌ Could not verify this channel. Please check the ID or username and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
                
                # Display the confirmation message
                display_name = info.get("title", str(channel_id))
                
                text = f"⚠️ FINAL WARNING ⚠️\n\n"
                text += f"You are about to delete ALL messages from:\n"
                text += f"Channel: {display_name}\n"
                text += f"ID: {channel_id}\n\n"
                text += f"This action is IRREVERSIBLE and will delete ALL messages in the channel.\n\n"
                text += f"Are you absolutely sure you want to proceed?"
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ YES, DELETE EVERYTHING", callback_data=f"execute_purge_{channel_id}"),
                    ],
                    [InlineKeyboardButton("❌ NO, CANCEL", callback_data="purge_channel_menu")]
                ]
                
                await update.message.reply_text(
                    text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            except Exception as e:
                logger.error(f"Error verifying channel: {str(e)}")
                await update.message.reply_text(
                    f"❌ Error verifying channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
                )
        except Exception as e:
            logger.error(f"Error processing channel input: {str(e)}")
            await update.message.reply_text(
                f"❌ Error: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="purge_channel_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)

async def setup_bot():
    """Set up the Telegram bot"""
    global bot_app
    
    # Create the application with faster polling for improved performance
    # Use a shorter polling timeout for faster updates (0.5s instead of default 1.0s)
    bot_app = Application.builder().token(BOT_TOKEN).build()
    
    # Configure polling with faster timeout for improved responsiveness
    # Reduced from 0.5s to 0.25s for even faster reposting
    bot_app.update_interval = 0.25
    
    # Complete workaround to avoid the blue start button
    # We don't register any command handler for /start at all
    # Instead, we only use alternative commands and a catch-all handler
    
    # First, register our alternative, non-standard commands
    bot_app.add_handler(CommandHandler("menu", start))
    bot_app.add_handler(CommandHandler("go", start))
    
    # Then define a catch-all text message handler that will check for /start
    # The priority is important - this should run before the regular text handler
    async def check_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message_text = update.message.text.strip()
        # Only match the exact /start command with optional bot username
        if message_text == "/start" or message_text.startswith("/start@"):
            await start(update, context)
            return
        # For all other messages, call the regular text handler
        await handle_text_input(update, context)
    
    # Add handler for stickers with highest priority (0)
    # This ensures sticker messages are processed before any other handlers
    print("==== REGISTERING STICKER HANDLER WITH PRIORITY 0 =====")
    sticker_handler = MessageHandler(filters.STICKER, handle_sticker_input)
    bot_app.add_handler(sticker_handler, 0)
    print(f"==== STICKER HANDLER REGISTERED: {sticker_handler} =====")
    print(f"==== TOTAL HANDLERS: {len(bot_app.handlers)} =====")
    
    # Debug - print all handlers
    for group_id, handlers_group in bot_app.handlers.items():
        print(f"==== HANDLER GROUP {group_id}: {len(handlers_group)} handlers =====")
        for handler in handlers_group:
            print(f"  - {handler}")
    
    # Add the catch-all handler with high priority (1)
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, check_start_command), 1)
    
    # Add the rest of the handlers
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    # We've already handled the text messages in the check_start_command function with higher priority
    
    # Initialize reposting_active flag
    bot_app.reposting_active = False
    
    # Start the bot
    await bot_app.initialize()
    await bot_app.start()
    
    logger.info("Bot has been set up and started")
    
    return bot_app

async def setup_client():
    """Set up the Telegram user client"""
    if not user_client:
        logger.error("Cannot set up user client: Missing API credentials or session")
        logger.warning("To use the bot for reposting, please set API_ID, API_HASH, and USER_SESSION environment variables")
        return None
        
    # Start the client
    await user_client.start()
    
    # Automatically join all destination channels to ensure we can send messages to them
    if active_channels["destination"]:
        # Join single destination if configured
        logger.info(f"Attempting to join destination channel: {active_channels['destination']}")
        try:
            result = await join_channel(user_client, active_channels['destination'])
            if result:
                logger.info(f"Successfully joined destination channel: {active_channels['destination']}")
            else:
                logger.error(f"Failed to join destination channel: {active_channels['destination']}")
        except Exception as e:
            logger.error(f"Error joining destination channel: {str(e)}")
            
    if active_channels["destinations"]:
        # Join multiple destinations if configured
        for dest in active_channels["destinations"]:
            logger.info(f"Attempting to join destination channel: {dest}")
            try:
                result = await join_channel(user_client, dest)
                if result:
                    logger.info(f"Successfully joined destination channel: {dest}")
                else:
                    logger.error(f"Failed to join destination channel: {dest}")
            except Exception as e:
                logger.error(f"Error joining destination channel: {str(e)}")
    
    # First remove all existing handlers if any exist
    if hasattr(user_client, '_event_builders'):
        builders = list(user_client._event_builders) if user_client._event_builders else []
        logger.info(f"Cleaning up {len(builders)} existing event handlers")
        for builder in builders:
            try:
                user_client.remove_event_handler(builder[1], builder[0])
            except Exception as e:
                logger.error(f"Error removing event handler: {e}")
    
    # Register a global event handler for debugging
    async def debug_all_events(event):
        logger.info(f"DEBUG: Received ANY event from ANY chat: {event.__class__.__name__}")
        logger.info(f"DEBUG: Chat ID: {event.chat_id if hasattr(event, 'chat_id') else 'Unknown'}")
        logger.info(f"DEBUG: Message: {event.message.text if hasattr(event, 'message') and hasattr(event.message, 'text') else 'No text'}")
        
    # Add this debugging handler
    user_client.add_event_handler(debug_all_events, events.NewMessage())
    logger.info("Registered global debug handler for ALL events")
    
    # Register event handlers if source channels are configured
    if active_channels["source"]:
        logger.info(f"Registering event handlers for source channels: {active_channels['source']}")
        
        # Register handler for new messages
        user_client.add_event_handler(
            handle_new_message,
            events.NewMessage(chats=active_channels["source"])
        )
        logger.info("Registered handler for new messages")
        
        # Register handler for edited messages
        user_client.add_event_handler(
            handle_edited_message,
            events.MessageEdited(chats=active_channels["source"])
        )
        logger.info("Registered handler for edited messages")
        
        # Register handler for deleted messages
        user_client.add_event_handler(
            handle_deleted_message,
            events.MessageDeleted(chats=active_channels["source"])
        )
        logger.info("Registered handler for message deletions")
    else:
        logger.warning("No source channels configured, event handler not registered")
    
    # Register handler for any incoming message (for debugging)
    logger.info("User client has been set up and started")
    
    return user_client

async def start_bot():
    """Start the bot and client"""
    try:
        # Set up the user client if credentials are available
        client = await setup_client()
        
        # Set up the bot
        bot = await setup_bot()
        
        # Run the bot until stopped
        await bot.updater.start_polling()
        
        # Keep the script running
        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Error starting bot: {str(e)}")
        raise
    
def run_bot():
    """Run the bot - used as a simple entry point in main.py"""
    pass  # We'll use a different approach from main.py

if __name__ == "__main__":
    run_bot()
