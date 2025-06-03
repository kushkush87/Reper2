#!/usr/bin/env python
import os
import sys
import logging
from dotenv import load_dotenv
import asyncio
from bot import run_bot
import argparse
from gen_session import generate_session

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def gen_session():
    """Run the session generator"""
    return await generate_session()

def print_header():
    """Print a nice header for the app"""
    print("\n" + "=" * 70)
    print(" 📡 TELEGRAM CHANNEL REPOSTER BOT")
    print(" 🔄 Repost content between channels without 'Forwarded from' tag")
    print(" 🏷️ Replace channel tags in messages to maintain original look")
    print("=" * 70 + "\n")

def print_help():
    """Print help information"""
    print("\nUsage:")
    print("  python run.py [command]")
    print("\nCommands:")
    print("  start       Start the Telegram bot (default if no command provided)")
    print("  session     Generate a new user session string")
    print("  help        Show this help message")
    print("\nExamples:")
    print("  python run.py start    # Start the bot")
    print("  python run.py session  # Generate a user session\n")

if __name__ == "__main__":
    print_header()
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(add_help=False, description='Telegram Channel Reposter Bot')
    parser.add_argument('command', nargs='?', default='start', 
                        help='Command to run (start, session, help)')
    
    args = parser.parse_args()
    
    if args.command == 'help':
        print_help()
    elif args.command == 'session':
        print("🔐 Starting session generator...\n")
        print("This will create a session string for your Telegram user account.")
        print("You'll need to provide your phone number and verify with a code.")
        print("\n⚠️ IMPORTANT: This gives full access to your account. Never share it!")
        print("-" * 70)
        try:
            asyncio.run(gen_session())
        except Exception as e:
            logger.error(f"Error generating session: {str(e)}")
    else:  # Default is 'start'
        logger.info("Starting Telegram Channel Reposter Bot...")
        try:
            # Check if session is available
            if not os.environ.get('USER_SESSION'):
                print("\n⚠️ Warning: USER_SESSION is not configured!")
                print("The bot will start, but with limited functionality.")
                print("To use the full features, generate a session by running:")
                print("  python run.py session\n")
            
            # Run the bot
            run_bot()
        except Exception as e:
            logger.error(f"Error starting bot: {str(e)}")