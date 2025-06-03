#!/usr/bin/env python
import os
import re
import sys

def set_session():
    """Set a USER_SESSION in the .env file"""
    print("\n=== TELEGRAM USER SESSION CONFIGURATOR ===\n")
    print("Please paste your session string below.")
    print("This is a long string of characters that you obtained from gen_session.py")
    print("or from another Telegram client app.\n")
    
    session_string = input("SESSION STRING: ").strip()
    
    if not session_string:
        print("❌ Error: No session string provided!")
        return
    
    if len(session_string) < 50:
        print("❌ Warning: This doesn't look like a valid session string (too short).")
        confirm = input("Continue anyway? (y/n): ").strip().lower()
        if confirm != 'y':
            print("Aborted.")
            return
    
    print("\nAdding session to .env file...")
    
    try:
        if os.path.exists(".env"):
            # Read the current file
            with open(".env", "r") as f:
                content = f.read()
            
            # Check if USER_SESSION already exists
            if "USER_SESSION=" in content:
                content = re.sub(
                    r'USER_SESSION=.*?(\n|$)',
                    f'USER_SESSION={session_string}\n',
                    content
                )
            else:
                # Add new session
                content += f'\nUSER_SESSION={session_string}\n'
            
            # Write back
            with open(".env", "w") as f:
                f.write(content)
        else:
            # Create new file
            with open(".env", "w") as f:
                f.write(f'USER_SESSION={session_string}\n')
        
        print("✅ Session has been successfully saved to .env file!")
        print("\nNext steps:")
        print("1. Restart the bot with 'python main.py'")
        print("2. Use /start in your Telegram bot chat")
        print("3. Configure your source and destination channels")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    set_session()