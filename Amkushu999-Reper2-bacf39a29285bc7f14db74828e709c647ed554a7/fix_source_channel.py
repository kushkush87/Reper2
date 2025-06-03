#!/usr/bin/env python
"""
Fix source channel handling in the Telegram Channel Reposter Bot
"""
import re
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def find_and_fix_source_channel_handling(file_path):
    """Find and fix the source channel int conversion in bot.py"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Regular expression to find and replace the vulnerable sections
    pattern1 = r'(\s+)# Try to convert to int \(for channel IDs\)\n(\s+)channel_id = int\(channel_input\)'
    replacement1 = r'\1# Try to convert to int (for channel IDs)\n\1try:\n\1    channel_id = int(channel_input)\n\1except ValueError:\n\1    # If we get here, we couldn\'t parse the channel in any known format\n\1    await update.message.reply_text(\n\1        "❌ Unable to understand the channel format. Please use a numeric ID (e.g., -1001234567890), " +\n\1        "a username (@channel), or a t.me link.",\n\1        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back to Menu", callback_data="back_to_menu")]])\n\1    )\n\1    context.user_data.pop("awaiting", None)\n\1    return'
    
    modified_content = re.sub(pattern1, replacement1, content)
    
    # Check if any changes were made
    if modified_content == content:
        logger.warning("No changes made to the file. Pattern may not have matched.")
        return False
    
    # Write the modified content back to the file
    with open(file_path, 'w') as f:
        f.write(modified_content)
    
    logger.info(f"Successfully fixed source channel handling in {file_path}")
    return True

def fix_start_command(file_path):
    """Add message cleanup to the start command"""
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Regular expression to find the start command function
    start_pattern = r'async def start\(update: Update, context: ContextTypes\.DEFAULT_TYPE\) -> None:\n\s+"""Start command handler with session information"""\n\s+# Get the message that triggered this command\n\s+trigger_message = update\.message\n\s+if trigger_message:\n\s+# Try to delete the message that called the /start command\n\s+try:\n\s+await trigger_message\.delete\(\)\n\s+logger\.info\(f"Deleted /start command message from user {trigger_message\.from_user\.id}"\)\n\s+except Exception as e:\n\s+logger\.error\(f"Failed to delete /start command message: {str\(e\)}"\)\n\s+# Continue even if deletion fails'
    
    start_replacement = r'''async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        user_message_history[user_id] = {}'''
    
    modified_content = re.sub(start_pattern, start_replacement, content)
    
    # Check if any changes were made
    if modified_content == content:
        logger.warning("No changes made to the start command. Pattern may not have matched.")
        return False
    
    # Write the modified content back to the file
    with open(file_path, 'w') as f:
        f.write(modified_content)
    
    logger.info(f"Successfully enhanced start command in {file_path}")
    return True

if __name__ == "__main__":
    logger.info("Starting to fix source channel handling in bot.py")
    success1 = find_and_fix_source_channel_handling("bot.py")
    success2 = fix_start_command("bot.py")
    
    if success1 and success2:
        logger.info("All fixes applied successfully")
    elif success1:
        logger.info("Only source channel handling was fixed")
    elif success2:
        logger.info("Only start command was enhanced")
    else:
        logger.warning("No fixes were applied - manual intervention may be needed")