"""
Fix the normalize_channel_id function in bot.py.
This script adds a properly working normalize_channel_id function to the bot.
"""

import re
import os
import logging
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   stream=sys.stdout)
logger = logging.getLogger(__name__)

# The fixed function to add
FIXED_FUNCTION = """
async def normalize_channel_id(channel_input):
    """Normalize channel input to a usable format for Telegram API"""
    import re  # Local import to ensure availability
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

def fix_normalize_channel_id():
    """Fix the normalize_channel_id function in bot.py"""
    try:
        with open("bot.py", "r") as file:
            content = file.read()
            
        # Find where the function is defined
        start_marker = "async def normalize_channel_id"
        start_pos = content.find(start_marker)
        
        if start_pos == -1:
            logger.error("Could not find normalize_channel_id function in bot.py")
            return False
            
        # Find end of function by looking for the next async def
        end_marker = "async def "
        end_pos = content.find(end_marker, start_pos + len(start_marker))
        
        if end_pos == -1:
            # Try a different approach to find the end
            end_marker = "# Initialize the Telegram user client"
            end_pos = content.find(end_marker, start_pos)
            
            if end_pos == -1:
                logger.error("Could not find end of normalize_channel_id function")
                return False
                
        # Create modified content with fixed function
        modified_content = content[:start_pos] + FIXED_FUNCTION + content[end_pos:]
        
        # Write modified content back to bot.py
        with open("bot.py", "w") as file:
            file.write(modified_content)
            
        logger.info("Successfully fixed normalize_channel_id function")
        return True
    except Exception as e:
        logger.error(f"Error fixing normalize_channel_id function: {str(e)}")
        return False

if __name__ == "__main__":
    print("Fixing normalize_channel_id function...")
    if fix_normalize_channel_id():
        print("✅ Successfully fixed normalize_channel_id function")
    else:
        print("❌ Failed to fix normalize_channel_id function")