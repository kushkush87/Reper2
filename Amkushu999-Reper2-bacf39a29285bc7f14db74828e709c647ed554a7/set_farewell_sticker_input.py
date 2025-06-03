#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", None)

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def set_farewell_sticker(sticker_id, add_to_list=True):
    """Set a farewell sticker ID in the constants module and bot config"""
    try:
        print(f"Setting farewell sticker: {sticker_id}, add to list: {add_to_list}")
        
        # Make sure directories exist
        os.makedirs("assets/stickers", exist_ok=True)
        
        # If constants.py doesn't exist yet, create it
        if not os.path.exists("assets/stickers/constants.py"):
            with open("assets/stickers/constants.py", "w") as f:
                f.write('"""Constants for stickers used by the bot"""\n\n')
                f.write(f'FAREWELL_STICKERS = ["{sticker_id}"]\n')
            
            # Create __init__.py files if needed
            if not os.path.exists("assets/__init__.py"):
                with open("assets/__init__.py", "w") as f:
                    pass
                    
            if not os.path.exists("assets/stickers/__init__.py"):
                with open("assets/stickers/__init__.py", "w") as f:
                    pass
                    
            print("Created constants.py with initial sticker")
            return True
        
        # Update constants.py file
        with open("assets/stickers/constants.py", "r") as f:
            content = f.read()

        # Parse the current list  
        if "FAREWELL_STICKERS = [" in content:
            # Extract the current list
            start_idx = content.find("FAREWELL_STICKERS = [")
            end_idx = content.find("]", start_idx)
            stickers_section = content[start_idx:end_idx+1]
            
            # Extract sticker IDs
            sticker_list_str = stickers_section.replace("FAREWELL_STICKERS = [", "").replace("]", "")
            sticker_items = [s.strip() for s in sticker_list_str.split(",") if s.strip()]
            current_stickers = [item.strip('"\'') for item in sticker_items]
            
            print(f"Current stickers: {current_stickers}")
            
            if add_to_list:
                if sticker_id not in current_stickers:
                    current_stickers.append(sticker_id)
                    print(f"Added sticker to list, now: {current_stickers}")
            else:
                # Replace the list with just the new sticker
                current_stickers = [sticker_id]
                print(f"Replaced stickers with: {current_stickers}")
                
            # Format the updated list
            stickers_formatted = ", ".join([f'"{s}"' for s in current_stickers])
            new_stickers_list = f'FAREWELL_STICKERS = [{stickers_formatted}]'
            
            # Replace in the file
            new_content = content.replace(stickers_section, new_stickers_list)
        else:
            # Add a new FAREWELL_STICKERS list
            new_content = content + f'\n\nFAREWELL_STICKERS = ["{sticker_id}"]\n'
        
        # Write the updated content
        with open("assets/stickers/constants.py", "w") as f:
            f.write(new_content)
            
        print("Successfully updated constants.py")
        
        # Also update BOT_CONFIG
        try:
            # Load or initialize BOT_CONFIG
            if os.path.exists("bot_config.json"):
                with open("bot_config.json", "r") as f:
                    bot_config = json.load(f)
            else:
                bot_config = {}
                
            # Update the sticker ID
            bot_config["farewell_sticker_id"] = sticker_id
            
            # Save the config
            with open("bot_config.json", "w") as f:
                json.dump(bot_config, f, indent=2)
                
            print("Successfully updated bot_config.json")
        except Exception as e:
            print(f"Error updating bot_config.json: {e}")
            
        return True
    except Exception as e:
        print(f"Error setting farewell sticker: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python set_farewell_sticker_input.py STICKER_ID [add|replace]")
        sys.exit(1)
        
    sticker_id = sys.argv[1]
    mode = "add" if len(sys.argv) < 3 else sys.argv[2]
    add_to_list = (mode.lower() == "add")
    
    asyncio.run(set_farewell_sticker(sticker_id, add_to_list))
    print("Sticker setting completed!")