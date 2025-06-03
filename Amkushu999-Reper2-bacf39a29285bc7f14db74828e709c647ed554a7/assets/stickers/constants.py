# Sticker constants for the Telegram bot

# Default farewell sticker ID (used when leaving a channel)
# This is a CATuDio waving goodbye sticker
FAREWELL_STICKER_ID = "CAACAgIAAxkBAAELR65j645BzPj-1pVthQmCrMK1j_JsxQACuRUAAubQyEs-8Sg8_BmPFi8E"

# List of farewell stickers to use when leaving a channel
# These will be used randomly when leaving a channel
FAREWELL_STICKERS = [
    # Original farewell sticker
    "CAACAgIAAxkBAAELR65j645BzPj-1pVthQmCrMK1j_JsxQACuRUAAubQyEs-8Sg8_BmPFi8E",
    
    # Custom stickers created from user's images/videos
    # These should be sticker IDs (starting with CAA) not file paths
    
    # Popular Telegram Stickers for farewell
    "CAACAgIAAxkBAAIDRF6E_XVwwLsLe0JoTLQw3TgCcQABEQACrQADVp29ChW6Q8aMnDZIGAQ",  # Wave goodbye
    "CAACAgIAAxkBAAIDRV6E_XpTL9s_cIxVy9gGW13AVDGWAAK-AANWnb0K18VE4irKlUsYBA",  # Sad goodbye
    "CAACAgIAAxkBAAIDRl6E_X6upUZeI_zCSY4dCO-mAAGKowACsgADVp29CrcV2siXGYWwGAQ",  # Leaving wave
    "CAACAgIAAxkBAAIDR16E_YQPwLOKYfL7Ob_9WbYOAAElgwACtQADVp29Ci-OLykzh6qDGAQ",  # Farewell
    "CAACAgIAAxkBAAIDSF6E_Yk6MTUiF5RxXikrsCkpO6ZKAAK4AANWnb0KiS4w33c-ZeoYBA",  # Blue tears
    "CAACAgIAAxkBAAIDSV6E_Y5bYrCLOsf05eU-UnQJ23DnAAK7AANWnb0KRuXX6a1xTDMYBA",  # Crying
    "CAACAgIAAxkBAAIDSl6E_ZT3JExOZ8UPs43KpfkAAeKvGQACugADVp29Cmd1v24o8GZRGAQ",  # Sad goodbye wave
    
    # Add more stickers here as they're created
]

# To add a new sticker to this list, use the update_farewell_sticker_constant function in bot.py
# Example: await update_farewell_sticker_constant("CAACAgIAA...", add_to_list=True)
