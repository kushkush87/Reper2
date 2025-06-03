"""
Fix channel format handling in the Telegram Channel Reposter Bot

This script adds improved support for different channel formats:
- Numeric IDs
- @usernames
- t.me links
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger(__name__)

def fix_source_channel_handler():
    """Fix source channel handler in handle_text_input function"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
        
        # Find the source_channel handler section
        start_marker = "if awaiting == \"source_channel\":"
        end_marker = "# Clear awaiting state\n        context.user_data.pop(\"awaiting\", None)"
        
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find source_channel handler in bot.py")
            return False
        
        # Find the section where channel formats are handled
        format_section_start = content.find("# Handle different channel input formats", start_pos)
        if format_section_start == -1:
            logger.error("Could not find channel format handling section")
            return False
        
        # Find end of format section (before verification starts)
        verify_section_start = content.find("# Verify the channel exists", format_section_start)
        if verify_section_start == -1:
            logger.error("Could not find verification section")
            return False
        
        # Create improved channel format handling code
        improved_format_handling = """            # Handle different channel input formats
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
                            f"❌ Error resolving channel from link: {str(e)}\\n\\n"
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
                            f"❌ Error resolving channel: {str(e)}\\n\\n"
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
"""
        
        # Replace the entire section
        modified_content = content[:format_section_start] + improved_format_handling + content[verify_section_start:]
        
        # Write the updated content back to the file
        with open("bot.py", "w") as file:
            file.write(modified_content)
            
        logger.info("Successfully updated source channel handler")
        return True
    
    except Exception as e:
        logger.error(f"Error updating source channel handler: {str(e)}")
        return False

def fix_destination_channel_handler():
    """Fix destination channel handler in handle_text_input function"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
        
        # Find the destination_channel handler section
        start_marker = "elif awaiting == \"destination_channel\":"
        
        start_pos = content.find(start_marker)
        if start_pos == -1:
            logger.error("Could not find destination_channel handler in bot.py")
            return False
        
        # Find the section where channel formats are handled
        format_section_start = content.find("# Handle different channel input formats", start_pos)
        if format_section_start == -1:
            logger.error("Could not find channel format handling section")
            return False
        
        # Find end of format section (before verification starts)
        verify_section_start = content.find("# Verify the channel exists", format_section_start)
        if verify_section_start == -1:
            logger.error("Could not find verification section")
            return False
        
        # Create improved channel format handling code (same as source handler)
        improved_format_handling = """            # Handle different channel input formats
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
                            f"❌ Error resolving channel from link: {str(e)}\\n\\n"
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
                            f"❌ Error resolving channel: {str(e)}\\n\\n"
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
"""
        
        # Replace the entire section
        modified_content = content[:format_section_start] + improved_format_handling + content[verify_section_start:]
        
        # Write the updated content back to the file
        with open("bot.py", "w") as file:
            file.write(modified_content)
            
        logger.info("Successfully updated destination channel handler")
        return True
    
    except Exception as e:
        logger.error(f"Error updating destination channel handler: {str(e)}")
        return False

if __name__ == "__main__":
    print("=== Fixing Channel Format Handling ===")
    source_result = fix_source_channel_handler()
    dest_result = fix_destination_channel_handler()
    
    if source_result and dest_result:
        print("✅ Successfully fixed channel format handling")
    else:
        print("❌ Failed to fix channel format handling")