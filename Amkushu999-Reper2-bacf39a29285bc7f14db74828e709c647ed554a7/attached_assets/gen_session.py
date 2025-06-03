import os
import asyncio
import logging
import sys
import re
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Use system env variables if available
ENV_API_ID = os.environ.get('API_ID')
ENV_API_HASH = os.environ.get('API_HASH')

async def generate_session():
    """Generate a Telegram user session string."""
    print("🔐 Starting Telegram User Session Generation...\n")
    print("This script will help you generate a session string for your Telegram user account.")
    print("You'll need to provide your phone number and verification code sent to your Telegram.")
    print("⚠️ IMPORTANT: This session gives full access to your Telegram account. Never share it!")
    print("=" * 70)
    
    # Get credentials
    if ENV_API_ID and ENV_API_HASH:
        print(f"✅ Using API credentials from environment variables")
        api_id = ENV_API_ID
        api_hash = ENV_API_HASH
    else:
        api_id = input("📝 Enter your API ID (or press Enter to use the one from .env): ")
        api_hash = input("📝 Enter your API Hash (or press Enter to use the one from .env): ")
        
        if not api_id or not api_hash:
            # Try to read from .env file
            try:
                with open('.env', 'r') as env_file:
                    env_content = env_file.read()
                    
                    # Extract API_ID
                    api_id_match = re.search(r'API_ID=(\d+)', env_content)
                    if api_id_match and not api_id:
                        api_id = api_id_match.group(1)
                        print(f"✅ Using API_ID from .env file")
                    
                    # Extract API_HASH
                    api_hash_match = re.search(r'API_HASH=([a-zA-Z0-9]+)', env_content)
                    if api_hash_match and not api_hash:
                        api_hash = api_hash_match.group(1)
                        print(f"✅ Using API_HASH from .env file")
            except Exception as e:
                logger.error(f"Failed to read .env file: {e}")
    
    if not api_id or not api_hash:
        print("❌ API credentials are required. Please provide API_ID and API_HASH.")
        return None
    
    # Get phone number
    phone = input("📱 Enter your phone number (with country code, e.g., +1234567890): ")
    
    # Create client with StringSession
    client = TelegramClient(StringSession(), api_id, api_hash)
    
    try:
        # Connect to Telegram servers
        print("🔄 Connecting to Telegram servers...")
        await client.connect()
        
        # Ensure user is authorized
        if not await client.is_user_authorized():
            print("📲 Sending verification code to your phone...")
            await client.send_code_request(phone)
            
            # Loop to handle invalid codes
            while True:
                verification_code = input("🔢 Enter the verification code sent to your Telegram: ")
                
                try:
                    await client.sign_in(phone, verification_code)
                    break  # Break the loop if sign-in successful
                except PhoneCodeInvalidError:
                    print("❌ Invalid verification code. Please try again.")
                except SessionPasswordNeededError:
                    # Two-step verification is enabled
                    print("🔐 Two-factor authentication detected.")
                    password = input("🔑 Enter your 2FA password: ")
                    await client.sign_in(password=password)
                    break
                except Exception as e:
                    print(f"❌ Error during sign-in: {e}")
                    return None
        
        # Get user info
        me = await client.get_me()
        
        # Get the session string
        session_string = client.session.save()
        
        print(f"\n✅ Successfully generated session for {me.first_name} {me.last_name if me.last_name else ''} (ID: {me.id})")
        print("\n📋 Your session string (already saved to .env file):")
        print("=" * 70)
        print(f"{session_string}")
        print("=" * 70)
        
        # Save to .env file
        try:
            if os.path.exists('.env'):
                with open('.env', 'r') as env_file:
                    env_content = env_file.read()
                
                # Check if USER_SESSION already exists
                if 'USER_SESSION=' in env_content:
                    # Replace existing value
                    env_content = re.sub(
                        r'USER_SESSION=.*', 
                        f'USER_SESSION={session_string}', 
                        env_content
                    )
                else:
                    # Add new entry
                    env_content += f'\nUSER_SESSION={session_string}'
                
                # Write back to file
                with open('.env', 'w') as env_file:
                    env_file.write(env_content)
                    
                print("✅ Session string has been automatically saved to .env file")
            else:
                # Create new .env file
                with open('.env', 'w') as env_file:
                    env_file.write(f'USER_SESSION={session_string}\n')
                print("✅ Created new .env file with your session string")
                
            # Set in current environment
            os.environ['USER_SESSION'] = session_string
            print("✅ Session has been set in the current environment")
            
        except Exception as e:
            print(f"❌ Failed to save session to .env file: {e}")
            print("Please manually add this session string to your .env file as USER_SESSION={session_string}")
        
        print("\n⚠️ IMPORTANT: NEVER share your session string with anyone!")
        print("It provides full access to your Telegram account.")
        
        # Instructions for next step
        print("\n🔄 Next steps:")
        print("1. The session has been automatically saved to your environment")
        print("2. Restart the bot to apply the new session")
        print("3. You can now configure source and destination channels")
        
        return session_string
        
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        return None
    finally:
        await client.disconnect()

if __name__ == "__main__":
    print("\n🤖 TELEGRAM SESSION GENERATOR 🤖\n")
    session_string = asyncio.run(generate_session())
    
    if session_string:
        print("\n🎉 Session generation complete! You can now restart the bot to use your new session.")
    else:
        print("\n❌ Failed to generate session. Please check the errors above and try again.")