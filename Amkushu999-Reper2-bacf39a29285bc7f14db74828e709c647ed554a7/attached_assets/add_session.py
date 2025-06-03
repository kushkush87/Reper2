#!/usr/bin/env python
import os
import re
import sys
import argparse

def add_session_to_env(session_string):
    """Add a session string to the .env file"""
    
    if not session_string:
        print("❌ Error: No session string provided!")
        return False
    
    print("🔍 Checking session string...")
    # Basic validation - session strings are long
    if len(session_string) < 20:
        print("❌ Error: The provided string is too short to be a valid session string!")
        return False
    
    print("📝 Adding session to .env file...")
    
    try:
        # Check if .env file exists
        if os.path.exists(".env"):
            # Read the current file
            with open(".env", "r") as f:
                content = f.read()
            
            # Check if USER_SESSION already exists
            if "USER_SESSION=" in content:
                # Replace existing value using regex
                import re
                content = re.sub(
                    r'USER_SESSION=.*(\n|$)',
                    f'USER_SESSION={session_string}\n',
                    content
                )
            else:
                # Add as new line
                content = content.rstrip() + f'\nUSER_SESSION={session_string}\n'
            
            # Write updated content back
            with open(".env", "w") as f:
                f.write(content)
        else:
            # Create new .env file
            with open(".env", "w") as f:
                f.write(f'USER_SESSION={session_string}\n')
        
        # Also set it in the current environment
        os.environ["USER_SESSION"] = session_string
        
        print("✅ Session string successfully added to .env file!")
        return True
    
    except Exception as e:
        print(f"❌ Error: Failed to update .env file: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add Telegram session string to .env file")
    parser.add_argument("session_string", nargs="?", help="The session string to add")
    
    args = parser.parse_args()
    
    # If no argument was provided, prompt the user for input
    if not args.session_string:
        print("\n🔐 TELEGRAM SESSION CONFIGURATOR")
        print("=" * 70)
        print("This tool will add your session string to the .env file.")
        print("⚠️ The session string gives full access to your Telegram account. Never share it!")
        print("-" * 70)
        session_string = input("📝 Please paste your session string here: ").strip()
    else:
        session_string = args.session_string
    
    success = add_session_to_env(session_string)
    
    if success:
        print("\n⭐ Next steps:")
        print("1. Restart the bot using the button on the Replit interface")
        print("2. Go to your Telegram bot and use /start to access the menu")
        print("3. Configure your source and destination channels")
    else:
        print("\n❌ Failed to add session. Please check the errors above and try again.")