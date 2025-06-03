"""
This module contains fixes for Telegram Channel Reposter Bot
"""

import re
import os
import json
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple, Union

# Setup logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Key fixes for the bot:

# 1. Fix source channel handling
def fix_source_channel_handler_code():
    """
    Returns a fixed version of the source channel handler code
    with proper error handling for invalid input.
    """
    return """    if awaiting == "source_channel":
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
            
            # Process t.me links
            if "t.me/" in channel_input or "telegram.me/" in channel_input:
                logger.info(f"Processing Telegram link: {channel_input}")
                # Extract the username or chat ID from the link
                t_me_pattern = r'(?:https?://)?(?:t|telegram)\.me/(?:joinchat/)?([a-zA-Z0-9_-]+)'
                t_me_match = re.match(t_me_pattern, channel_input)
                
                if t_me_match:
                    username_or_code = t_me_match.group(1)
                    logger.info(f"Extracted username/code from link: {username_or_code}")
                    
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(username_or_code)
                        channel_id = entity.id
                    except Exception as e:
                        await update.message.reply_text(
                            f"❌ Error resolving channel from link: {str(e)}\\n\\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                else:
                    await update.message.reply_text(
                        "❌ Invalid Telegram link format.\\n\\n"
                        "Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Process @username format
            elif channel_input.startswith('@'):
                logger.info(f"Processing username: {channel_input}")
                try:
                    # Try to resolve the username to an ID
                    entity = await user_client.get_entity(channel_input)
                    channel_id = entity.id
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Error resolving channel: {str(e)}\\n\\n"
                        f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            else:
                # Try to convert to int (for channel IDs)
                try:
                    channel_id = int(channel_input)
                except ValueError:
                    # If we get here, we couldn't parse the channel in any known format
                    await update.message.reply_text(
                        "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                        "a username (@channel), or a t.me link.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "❌ Could not verify this channel. Please check the ID or username and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
                
                # Try to join the channel if needed
                await join_channel(user_client, channel_id)
                
                # Add to source channels if not already present
                if channel_id not in active_channels["source"]:
                    active_channels["source"].append(channel_id)
                    await save_config()
                    await update.message.reply_text(
                        f"✅ Added {info.get('title', channel_id)} to source channels.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                else:
                    await update.message.reply_text(
                        "ℹ️ This channel is already in your source list.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error adding channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error processing channel: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)"""

# 2. Fix destination channel handler code
def fix_destination_channel_handler_code():
    """
    Returns a fixed version of the destination channel handler code
    with proper error handling for invalid input.
    """
    return """    elif awaiting == "destination_channel":
        # Handle destination channel input
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
            
            # Process t.me links
            if "t.me/" in channel_input or "telegram.me/" in channel_input:
                logger.info(f"Processing Telegram link: {channel_input}")
                # Extract the username or chat ID from the link
                t_me_pattern = r'(?:https?://)?(?:t|telegram)\.me/(?:joinchat/)?([a-zA-Z0-9_-]+)'
                t_me_match = re.match(t_me_pattern, channel_input)
                
                if t_me_match:
                    username_or_code = t_me_match.group(1)
                    logger.info(f"Extracted username/code from link: {username_or_code}")
                    
                    try:
                        # Try to resolve the username to an ID
                        entity = await user_client.get_entity(username_or_code)
                        channel_id = entity.id
                    except Exception as e:
                        await update.message.reply_text(
                            f"❌ Error resolving channel from link: {str(e)}\\n\\n"
                            f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                        )
                        context.user_data.pop("awaiting", None)
                        return
                else:
                    await update.message.reply_text(
                        "❌ Invalid Telegram link format.\\n\\n"
                        "Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
                    
            # Process @username format
            elif channel_input.startswith('@'):
                try:
                    # Try to resolve the username to an ID
                    entity = await user_client.get_entity(channel_input)
                    channel_id = entity.id
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Error resolving channel: {str(e)}\\n\\n"
                        f"Please try using a numeric channel ID instead (e.g., -1001234567890).",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            else:
                # Try to convert to int (for channel IDs)
                try:
                    channel_id = int(channel_input)
                except ValueError:
                    # If we get here, we couldn't parse the channel in any known format
                    await update.message.reply_text(
                        "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +
                        "a username (@channel), or a t.me link.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
            
            # Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "❌ Could not verify this channel. Please check the ID or username and try again.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                    )
                    context.user_data.pop("awaiting", None)
                    return
                
                # Check if the user has post permission
                # This won't be 100% reliable but can help prevent obvious mistakes
                try:
                    # Try to get admin rights
                    admin_rights = await user_client.get_permissions(channel_id)
                    
                    # Check if the user has post permission
                    if not admin_rights.post_messages:
                        await update.message.reply_text(
                            f"⚠️ Warning: You may not have permission to post in {info.get('title', channel_id)}. "
                            f"The reposting might fail.\\n\\n"
                            f"Would you like to use this channel anyway?",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("✅ Yes, use anyway", callback_data=f"force_dest_{channel_id}")],
                                [InlineKeyboardButton("❌ No, cancel", callback_data="back_to_menu")]
                            ])
                        )
                        # Store the channel info in user data for the callback
                        context.user_data["temp_destination"] = {
                            "id": channel_id,
                            "title": info.get('title', str(channel_id))
                        }
                        return
                except Exception as perm_error:
                    logger.warning(f"Could not check permissions for channel {channel_id}: {str(perm_error)}")
                    # Continue anyway
                
                # Set as destination channel
                active_channels["destination"] = channel_id
                await save_config()
                
                await update.message.reply_text(
                    f"✅ Set {info.get('title', channel_id)} as destination channel.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error setting destination channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error processing channel: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)"""

# 3. Fix the API ID setting code
def fix_api_id_handling_code():
    """
    Returns a fixed version of the API ID handling code to ensure it's an integer.
    """
    return """    elif awaiting == "api_id":
        try:
            # Validate API ID format (should be a numeric value)
            api_id = update.message.text.strip()
            if not api_id.isdigit():
                await update.message.reply_text(
                    "❌ API ID must be a numeric value. Please try again.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                return
                
            # Convert to integer and store
            api_id_int = int(api_id)
            os.environ["API_ID"] = api_id
            
            # Update the .env file
            try:
                with open(".env", "r") as env_file:
                    env_content = env_file.read()
                
                if "API_ID=" in env_content:
                    new_env_content = re.sub(r'API_ID=.*', f'API_ID={api_id}', env_content)
                else:
                    new_env_content = env_content + f'\\nAPI_ID={api_id}'
                
                with open(".env", "w") as env_file:
                    env_file.write(new_env_content)
            except Exception as e:
                logger.error(f"Failed to update .env file with API_ID: {str(e)}")
            
            # Update global variable
            global API_ID
            API_ID = api_id_int
            
            # Ask for API hash next
            await update.message.reply_text(
                "✅ API ID saved. Now, please send your API Hash."
            )
            context.user_data["awaiting"] = "api_hash"
        except Exception as e:
            await update.message.reply_text(
                f"❌ Error saving API ID: {str(e)}. Please try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
            context.user_data.pop("awaiting", None)"""

# 4. Improved start command with complete message cleanup
def fix_start_command():
    """
    Returns an improved /start command implementation with full message cleanup.
    """
    return """async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
    
    # Create buttons for main menu
    menu_buttons = []
    
    # Source channel buttons
    menu_buttons.append([InlineKeyboardButton("📥 Add Source Channel", callback_data="add_source")])
    
    # Only show the "View Source Channels" button if there are any
    if active_channels["source"]:
        menu_buttons.append([InlineKeyboardButton("📋 View Source Channels", callback_data="view_sources")])
    
    # Destination channel button
    dest_text = "📤 Set Destination Channel"
    if active_channels["destination"]:
        # Try to get destination channel info if we have a user client
        if user_client and user_client.is_connected():
            try:
                dest_info = await get_entity_info(user_client, active_channels["destination"])
                if dest_info and dest_info.get("title"):
                    dest_text = f"📤 Destination: {dest_info['title']}"
            except Exception as e:
                logger.error(f"Error getting destination channel info: {str(e)}")
                # Use default text
    
    menu_buttons.append([InlineKeyboardButton(dest_text, callback_data="set_destination")])
    
    # Tag replacement buttons
    menu_buttons.append([InlineKeyboardButton("🏷️ Channel Tags", callback_data="manage_tags")])
    
    # Admin config button
    menu_buttons.append([InlineKeyboardButton("👤 Admin Users", callback_data="manage_admins")])
    
    # API config button - show status
    api_text = "⚙️ Configure API"
    if API_ID and API_HASH and USER_SESSION:
        api_text = "⚙️ API: Configured ✅"
    else:
        missing = []
        if not API_ID:
            missing.append("API_ID")
        if not API_HASH:
            missing.append("API_HASH")
        if not USER_SESSION:
            missing.append("USER_SESSION")
        
        if missing:
            api_text = f"⚙️ API: Missing {', '.join(missing)} ❌"
    
    menu_buttons.append([InlineKeyboardButton(api_text, callback_data="config_api")])
    
    # Status button shows if everything is ready
    status_text = "❌ Bot Not Ready"
    if (API_ID and API_HASH and USER_SESSION and 
        active_channels["source"] and active_channels["destination"]):
        status_text = "✅ Bot Ready"
    
    menu_buttons.append([InlineKeyboardButton(status_text, callback_data="check_status")])
    
    # Create reply markup
    reply_markup = InlineKeyboardMarkup(menu_buttons)
    
    # Get bot image path
    image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "bot_logo.jpg")
    if not os.path.exists(image_path):
        # Fall back to a default image if the logo is not found
        image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "default_logo.jpg")
        if not os.path.exists(image_path):
            # If no default image is found, don't use an image
            image_path = None
    
    # Send welcome message with the inline keyboard
    welcome_text = (
        "Welcome to the Channel Reposter Bot!\n\n"
        "This bot reposts content from source channels to a destination channel "
        "without the forward tag, and can replace channel tags with custom values.\n\n"
        "Current Status:\n"
    )
    
    # Add API status
    if API_ID and API_HASH and USER_SESSION:
        welcome_text += "✅ API credentials configured\n"
    else:
        welcome_text += "❌ API credentials not configured\n"
    
    # Add source channels status
    if active_channels["source"]:
        welcome_text += f"✅ Source channels: {len(active_channels['source'])} configured\n"
    else:
        welcome_text += "❌ No source channels configured\n"
    
    # Add destination channel status
    if active_channels["destination"]:
        welcome_text += "✅ Destination channel configured\n"
    else:
        welcome_text += "❌ No destination channel configured\n"
    
    # Add tag replacements status
    if tag_replacements:
        welcome_text += f"✅ Tag replacements: {len(tag_replacements)} configured\n"
    else:
        welcome_text += "ℹ️ No tag replacements configured (optional)\n"
    
    # Add status and instructions
    if (API_ID and API_HASH and USER_SESSION and 
        active_channels["source"] and active_channels["destination"]):
        welcome_text += "\n✅ Bot is ready and monitoring source channels!"
    else:
        welcome_text += "\n❌ Please configure the missing settings to start monitoring."
    
    # Send message with photo if available, otherwise just text
    if image_path:
        sent_message = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=open(image_path, "rb"),
            caption=welcome_text,
            reply_markup=reply_markup
        )
    else:
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_text,
            reply_markup=reply_markup
        )
    
    # Store message ID for later cleanup
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Initialize user tracking if needed
    if user_id not in user_message_history:
        user_message_history[user_id] = {}
    if chat_id not in user_message_history[user_id]:
        user_message_history[user_id][chat_id] = []
    
    # Add this message to the tracking
    user_message_history[user_id][chat_id].append(sent_message.message_id)
    logger.info(f"Added message {sent_message.message_id} to tracking for user {user_id} in chat {chat_id}")"""

# 5. Improved back_to_menu function
def fix_back_to_menu_function():
    """
    Returns an improved back_to_menu function implementation 
    that properly cleans up all messages.
    """
    return """async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Go back to the main menu"""
    # Get the callback query
    query = update.callback_query
    await query.answer()
    
    # Clear any awaiting state
    context.user_data.pop("awaiting", None)
    
    # User ID for message tracking
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Delete all existing messages for this user in this chat
    if user_id in user_message_history and chat_id in user_message_history[user_id]:
        for msg_id in user_message_history[user_id][chat_id]:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
                logger.info(f"Deleted message {msg_id} in chat {chat_id} for user {user_id}")
            except Exception as e:
                logger.warning(f"Failed to delete message {msg_id} in chat {chat_id}: {str(e)}")
        
        # Clear the tracking for this user in this chat
        user_message_history[user_id][chat_id] = []
    
    # Call the start command to show the main menu
    await start(update, context)"""

# 6. Fix for initialization of the user client
def fix_init_user_client():
    """
    Returns an improved initialization for the user client
    with proper error handling and validation.
    """
    return """# Initialize the Telegram user client with the session if credentials are available
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
        # Still keep the client as None in case of errors"""

def get_instruction():
    """
    Returns instructions on how to apply the fixes
    """
    return """
To apply these fixes, follow these steps:

1. First, copy the fixes into a new file (this file).
2. Replace the appropriate sections in bot.py with the fixed versions:
   - Replace the source channel handler code
   - Replace the destination channel handler code
   - Replace the API ID handling code
   - Replace the start command implementation
   - Replace the back_to_menu function
   - Replace the user client initialization code

These fixes will:
1. Add proper error handling for invalid channel formats
2. Ensure the API_ID is always treated as an integer
3. Fix clearing of old messages when showing the main menu
4. Improve the display of status information
5. Make sure the start command deletes all old messages
"""

# Main instruction 
if __name__ == "__main__":
    print(get_instruction())