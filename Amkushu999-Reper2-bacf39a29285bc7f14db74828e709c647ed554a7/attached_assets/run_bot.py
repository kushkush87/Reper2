#!/usr/bin/env python3
import os
import asyncio
import logging
import sys
from bot import setup_bot, BOT_TOKEN
from telegram.ext import Application

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """Main function to start the bot"""
    try:
        logger.info("Starting the bot...")
        
        # Import only what we need directly
        from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
        from bot import start, button_callback, handle_text_input
        
        # Initialize the bot
        application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers directly
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        
        # Start the bot
        logger.info("Bot started. Polling for updates...")
        await application.start()
        
        # Run polling in the current thread/process
        await application.updater.start_polling()
        
        # Keep application running
        running = True
        while running:
            try:
                await asyncio.sleep(1)
            except KeyboardInterrupt:
                running = False
        
        # Cleanup when done
        await application.updater.stop_polling()
        await application.stop()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())