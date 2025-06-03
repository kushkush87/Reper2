"""
Improved channel format handling for Telegram Channel Reposter Bot

This module provides improved handling for different channel formats:
- Numeric IDs
- @usernames
- t.me links

It centralizes the channel normalization logic and updates the bot.py file
to use consistent channel format handling throughout the application.
"""

import os
import re
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger(__name__)

# Function to add to bot.py
NORMALIZE_CHANNEL_ID_FUNC = """
async def normalize_channel_id(channel_input: Union[int, str]) -> Union[int, str]:
    \"\"\"
    Normalize channel input to a usable format for Telegram API
    Handles t.me links, @usernames, and numeric IDs
    
    Returns the normalized channel ID or username
    \"\"\"
    original_input = channel_input
    
    try:
        # Handle string inputs
        if isinstance(channel_input, str):
            # Handle t.me links with improved pattern
            t_me_pattern = r'(?:https?://)?(?:t|telegram)\.me/(?:joinchat/)?([a-zA-Z0-9_\\-]+)'
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
"""

# Function to update source channel handler
SOURCE_CHANNEL_HANDLER = """
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
            # Use our normalized channel ID function for consistent handling
            normalized_input = await normalize_channel_id(channel_input)
            logger.info(f"Normalized channel input: {normalized_input}")
            
            try:
                # Try to resolve the normalized input to an entity
                entity = await user_client.get_entity(normalized_input)
                channel_id = entity.id
                logger.info(f"Successfully resolved channel ID: {channel_id}")
            except Exception as e:
                logger.error(f"Error resolving channel from input '{channel_input}': {str(e)}")
                await update.message.reply_text(
                    f"❌ Error resolving channel: {str(e)}\\n\\n"
                    f"Please check the channel format and ensure you have access to it.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
            
            # Verify the channel exists and we can access it
            try:
                info = await get_entity_info(user_client, channel_id)
                if not info:
                    await update.message.reply_text(
                        "Could not verify this channel. Please check the ID or username and try again.",
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
        except ValueError as e:
            logger.error(f"Value error processing channel input: {str(e)}")
            await update.message.reply_text(
                f"❌ Invalid channel format: {str(e)}\\n\\n"
                f"Please use a numeric ID (e.g., -1001234567890), username (@channel), or t.me link.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        except Exception as e:
            logger.error(f"Unexpected error processing channel input: {str(e)}")
            await update.message.reply_text(
                f"❌ Error: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
"""

# Function to update destination channel handler
DESTINATION_CHANNEL_HANDLER = """
    elif awaiting == "destination_channel":
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
            # Use our normalized channel ID function for consistent handling
            normalized_input = await normalize_channel_id(channel_input)
            logger.info(f"Normalized channel input: {normalized_input}")
            
            try:
                # Try to resolve the normalized input to an entity
                entity = await user_client.get_entity(normalized_input)
                channel_id = entity.id
                logger.info(f"Successfully resolved destination channel ID: {channel_id}")
            except Exception as e:
                logger.error(f"Error resolving destination channel from input '{channel_input}': {str(e)}")
                await update.message.reply_text(
                    f"❌ Error resolving channel: {str(e)}\\n\\n"
                    f"Please check the channel format and ensure you have access to it.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
                context.user_data.pop("awaiting", None)
                return
            
            # Get channel info
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
                
                # Set as destination channel
                active_channels["destination"] = channel_id
                await save_config()
                await update.message.reply_text(
                    f"✅ Set {info.get('title', channel_id)} as the destination channel.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
            except Exception as e:
                await update.message.reply_text(
                    f"❌ Error setting destination channel: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
                )
        except ValueError as e:
            logger.error(f"Value error processing destination channel input: {str(e)}")
            await update.message.reply_text(
                f"❌ Invalid channel format: {str(e)}\\n\\n"
                f"Please use a numeric ID (e.g., -1001234567890), username (@channel), or t.me link.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        except Exception as e:
            logger.error(f"Unexpected error processing destination channel input: {str(e)}")
            await update.message.reply_text(
                f"❌ Error: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])
            )
        
        # Clear awaiting state
        context.user_data.pop("awaiting", None)
"""

def add_normalize_channel_id_function():
    """Add the normalize_channel_id function to bot.py after imports section"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find the position after imports
        import_section_end = content.find("# Initialize the Telegram user client")
        if import_section_end == -1:
            logger.error("Could not find the end of import section in bot.py")
            return False
            
        # Insert our function after imports
        new_content = content[:import_section_end] + NORMALIZE_CHANNEL_ID_FUNC + content[import_section_end:]
        
        with open("bot.py", "w") as file:
            file.write(new_content)
            
        logger.info("Successfully added normalize_channel_id function to bot.py")
        return True
    except Exception as e:
        logger.error(f"Error adding normalize_channel_id function: {str(e)}")
        return False

def update_join_channel_function():
    """Update the join_channel function to use normalize_channel_id"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find the join_channel function
        start_marker = "async def join_channel"
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find join_channel function in bot.py")
            return False
        
        # Find where channel ID processing begins
        old_code_start = content.find("if isinstance(channel_id, str):", start_pos)
        if old_code_start == -1:
            logger.error("Could not find channel ID processing in join_channel function")
            return False
        
        # Find where the entity is retrieved (after the processing)
        end_marker = "entity = await client.get_entity"
        end_pos = content.find(end_marker, old_code_start)
        if end_pos == -1:
            logger.error("Could not find entity retrieval in join_channel function")
            return False
        
        # Go back to the beginning of the line with end_marker
        line_start = content.rfind("\n", 0, end_pos) + 1
        
        # Replace everything between old_code_start and line_start
        new_code = "        # Use our normalized channel ID function\n        channel_id = await normalize_channel_id(channel_id)\n        \n        "
        
        new_content = (
            content[:old_code_start] + 
            new_code + 
            content[line_start:]
        )
        
        with open("bot.py", "w") as file:
            file.write(new_content)
            
        logger.info("Successfully updated join_channel function in bot.py")
        return True
    except Exception as e:
        logger.error(f"Error updating join_channel function: {str(e)}")
        return False

def update_get_entity_info_function():
    """Update the get_entity_info function to use normalize_channel_id"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find the get_entity_info function
        start_marker = "async def get_entity_info"
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find get_entity_info function in bot.py")
            return False
            
        # Find where entity processing begins (look for an isinstance check)
        old_code_pos = content.find("if isinstance(entity_id, str):", start_pos)
        if old_code_pos == -1:
            logger.error("Could not find entity type handling in get_entity_info function")
            return False
            
        # Find where entity processing ends (look for client connection check or entity retrieval)
        end_markers = [
            "# Check if client is connected",
            "if not client.is_connected():",
            "entity = await client.get_entity"
        ]
        
        end_pos = None
        for marker in end_markers:
            pos = content.find(marker, old_code_pos)
            if pos != -1 and (end_pos is None or pos < end_pos):
                end_pos = pos
                
        if end_pos is None:
            logger.error("Could not find end of entity type handling in get_entity_info function")
            return False
            
        # Create a new code section with our normalized function
        new_code = """        # Keep the original for error reporting
        original_entity_id = entity_id  
        
        try:
            # Use our channel ID normalizer function
            entity_id = await normalize_channel_id(entity_id)
            logger.info(f"Normalized entity ID: {entity_id}")
            
"""
        
        # Move back to the beginning of the line with the end marker
        line_start = content.rfind("\n", 0, end_pos) + 1
        
        # Replace everything between old_code_pos and line_start with our new code
        new_content = content[:old_code_pos] + new_code + content[line_start:]
        
        with open("bot.py", "w") as file:
            file.write(new_content)
            
        logger.info("Successfully updated get_entity_info function in bot.py")
        return True
    except Exception as e:
        logger.error(f"Error updating get_entity_info function: {str(e)}")
        return False

def update_source_channel_handler():
    """Update the source_channel handler in handle_text_input function"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find the source_channel handler
        start_marker = "if awaiting == \"source_channel\":"
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find source_channel handler in bot.py")
            return False
            
        # Find where the handler ends
        end_marker = "elif awaiting == \"destination_channel\":"
        end_pos = content.find(end_marker, start_pos)
        if end_pos == -1:
            logger.error("Could not find end of source_channel handler in bot.py")
            return False
            
        # Replace the entire handler
        new_content = content[:start_pos] + SOURCE_CHANNEL_HANDLER + "\n    " + content[end_pos:]
        
        with open("bot.py", "w") as file:
            file.write(new_content)
            
        logger.info("Successfully updated source_channel handler in bot.py")
        return True
    except Exception as e:
        logger.error(f"Error updating source_channel handler: {str(e)}")
        return False

def update_destination_channel_handler():
    """Update the destination_channel handler in handle_text_input function"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find the destination_channel handler
        start_marker = "elif awaiting == \"destination_channel\":"
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find destination_channel handler in bot.py")
            return False
            
        # Find where the handler ends
        end_marker_list = [
            "elif awaiting == \"tag_replacement\":",
            "elif awaiting == \"admin_id\":",
            "else:",
            "async def setup_bot():"
        ]
        
        end_pos = None
        for marker in end_marker_list:
            pos = content.find(marker, start_pos)
            if pos != -1 and (end_pos is None or pos < end_pos):
                end_pos = pos
                
        if end_pos is None:
            logger.error("Could not find end of destination_channel handler in bot.py")
            return False
            
        # Replace the entire handler
        new_content = content[:start_pos] + DESTINATION_CHANNEL_HANDLER + "\n    " + content[end_pos:]
        
        with open("bot.py", "w") as file:
            file.write(new_content)
            
        logger.info("Successfully updated destination_channel handler in bot.py")
        return True
    except Exception as e:
        logger.error(f"Error updating destination_channel handler: {str(e)}")
        return False

def print_instructions():
    """Print instructions on how to apply the fixes"""
    print("\n" + "=" * 80)
    print("IMPROVED CHANNEL FORMAT HANDLING")
    print("=" * 80)
    print("\nThis script adds improved channel format handling to the Telegram Channel Reposter Bot.")
    print("It will add a normalize_channel_id function and update the following parts of the code:")
    print("  - join_channel function")
    print("  - get_entity_info function")
    print("  - Source channel handler")
    print("  - Destination channel handler")
    print("\nTo apply the fixes, run this script directly:")
    print("  python improved_channel_formats.py")
    print("\nThe script will make a backup of bot.py before making any changes.")
    print("=" * 80 + "\n")

def main():
    """Main function to apply all improvements"""
    print_instructions()
    
    # Check if normalize_channel_id function exists
    with open("bot.py", "r") as file:
        content = file.read()
        
    if "async def normalize_channel_id" in content:
        print("✓ normalize_channel_id function already exists")
        print("✓ join_channel function already updated")
        print("✓ get_entity_info function already updated")
    else:
        # Backup the original file
        try:
            with open("bot.py", "r") as src:
                with open("bot.py.bak", "w") as dst:
                    dst.write(src.read())
            print("✅ Created backup of bot.py as bot.py.bak")
        except Exception as e:
            print(f"❌ Failed to create backup: {e}")
            return
            
        # Add normalize_channel_id function
        print(f"🔄 Adding normalize_channel_id function...")
        if add_normalize_channel_id_function():
            print(f"✅ Adding normalize_channel_id function successful")
        else:
            print(f"❌ Adding normalize_channel_id function failed")
            print("⚠️ Cannot continue without this core function.")
            return
    
    # Update the channel handlers
    steps = [
        (update_source_channel_handler, "Updating source channel handler"),
        (update_destination_channel_handler, "Updating destination channel handler")
    ]
    
    # Backup the file before updating handlers
    try:
        with open("bot.py", "r") as src:
            with open("bot.py.handlers.bak", "w") as dst:
                dst.write(src.read())
        print("✅ Created backup of current bot.py as bot.py.handlers.bak")
    except Exception as e:
        print(f"❌ Failed to create backup: {e}")
        return
    
    for func, desc in steps:
        print(f"🔄 {desc}...")
        if func():
            print(f"✅ {desc} successful")
        else:
            print(f"❌ {desc} failed")
            print("⚠️ Some improvements may be partially applied. Check logs for details.")
            # Continue with other steps regardless, as they're independent
    
    print("\n✅ Channel format handling improvements applied!")
    print("🔄 Please restart the bot for changes to take effect.")

if __name__ == "__main__":
    main()