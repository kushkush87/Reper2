#!/usr/bin/env python3
"""
Simplified Telegram bot that focuses just on the telegram-bot-python functionality
without attempting to use Telethon simultaneously.
"""
import os
import sys
import asyncio
import logging
import signal
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    CallbackQueryHandler, 
    MessageHandler, 
    filters,
    ContextTypes
)

# Load environment variables
load_dotenv()
BOT_TOKEN = os.environ.get("BOT_TOKEN", None)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Shutdown flag
shutdown_flag = False

# Dictionary to store active channels 
# Note: This is in-memory only, no persistence
active_channels = {
    "source": None,
    "sources": [],
    "destination": None,
    "destinations": []
}

def signal_handler(sig, frame):
    """Handle interrupt signals"""
    global shutdown_flag
    logger.info(f"Received signal {sig}, initiating shutdown...")
    shutdown_flag = True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command handler"""
    user = update.effective_user
    logger.info(f"User {user.id} ({user.username}) started the bot")
    
    # Welcome message
    text = f"👋 Hello {user.first_name}!\n\n"
    text += "This is a simplified version of the Telegram Channel Reposter Bot.\n\n"
    text += "⚠️ Notice: The full bot features that require Telethon are currently unavailable.\n"
    text += "This simple bot only provides basic menu functionality.\n\n"
    text += "Please use the full bot version for channel operations."
    
    # Main menu keyboard
    keyboard = [
        [InlineKeyboardButton("Channel Settings", callback_data="channel_settings_menu")],
        [InlineKeyboardButton("Bot Status", callback_data="bot_status")]
    ]
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "channel_settings_menu":
        # Channel settings menu
        text = "⚙️ Channel Settings\n\n"
        text += "Configure settings for channel management functionality:\n"
        text += "\nNote: Channel management is disabled in this simplified version."
        
        keyboard = [
            [InlineKeyboardButton("📊 View Current Settings", callback_data="view_channel_settings")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "view_channel_settings":
        # View current channel settings
        text = "📊 Channel Management Settings\n\n"
        text += "To manage stickers, use `python set_farewell_sticker_input.py` in the Replit terminal."
        text += "\n\nNote: Full functionality is disabled in this simplified version."
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Channel Settings", callback_data="channel_settings_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "bot_status":
        # Bot status
        text = "🤖 Bot Status\n\n"
        text += "✅ Bot is running\n"
        text += "✅ Telegram Bot API connection OK\n"
        text += "⚠️ Telethon connection unavailable\n\n"
        text += "This is a simplified version of the bot with limited functionality."
        
        keyboard = [
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="main_menu")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == "main_menu":
        # Back to main menu
        text = "📋 Main Menu\n\n"
        text += "Please select an option:"
        
        keyboard = [
            [InlineKeyboardButton("Channel Settings", callback_data="channel_settings_menu")],
            [InlineKeyboardButton("Bot Status", callback_data="bot_status")]
        ]
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input"""
    # Just acknowledge the message
    await update.message.reply_text(
        "⚠️ Text command processing is disabled in this simplified version.\n"
        "Please use the menu buttons or commands."
    )

async def handle_sticker_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle sticker input"""
    # Just acknowledge the sticker
    sticker_id = update.message.sticker.file_id
    await update.message.reply_text(
        f"✅ Received sticker with ID: {sticker_id}\n\n"
        "⚠️ Sticker processing is disabled in this simplified version.\n"
        "Please use `python set_farewell_sticker_input.py` in the Replit terminal."
    )

async def run_bot():
    """Run the Telegram bot"""
    logger.info("Starting simplified Telegram bot...")
    
    try:
        # Build the application
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("menu", start))
        
        # Add callback handler
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add message handlers
        application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker_input))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        
        # Start the application
        await application.initialize()
        await application.start()
        await application.updater.start_polling(poll_interval=0.5)
        
        logger.info("✅ Simplified bot is now running")
        
        # Keep the bot running
        while not shutdown_flag:
            await asyncio.sleep(1)
            
        # Clean shutdown
        logger.info("Shutting down bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        logger.info("Bot has been shut down")
        
    except Exception as e:
        logger.error(f"Error in bot: {e}", exc_info=True)
        return 1
    
    return 0

def main():
    """Main entry point"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Set up the event loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        exit_code = loop.run_until_complete(run_bot())
    finally:
        # Clean up
        loop.close()
    
    return exit_code

if __name__ == "__main__":
    sys.exit(main())