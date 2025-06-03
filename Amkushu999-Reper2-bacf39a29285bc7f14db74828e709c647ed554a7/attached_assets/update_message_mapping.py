#!/usr/bin/env python3
"""
Script to update message mapping code to use memory-efficient function
"""

import re

def update_mapping_code(file_path):
    # Read the file
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Pattern to find the message mapping code that needs to be updated
    pattern = r"""if not is_edit and source_channel_id and source_message_id and dest_message:
\s+dest_msg_id = dest_message\.id
\s+key = \(source_channel_id, source_message_id\)
\s+if key not in message_mapping:
\s+message_mapping\[key\] = \{\}
\s+message_mapping\[key\]\[dest_channel\] = dest_msg_id
\s+sent_destinations\[dest_channel\] = dest_msg_id
\s+logger\.info\(f"Mapped source message \(\{source_channel_id\}, \{source_message_id\}\) to destination \(\{dest_channel\}, \{dest_msg_id\}\)"\)"""
    
    # The replacement code
    replacement = """if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            # Use memory-efficient mapping function
                            await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                            sent_destinations[dest_channel] = dest_msg_id"""
    
    # Find all matches and update
    updated_content = re.sub(pattern, replacement, content)
    
    # Check if we made any changes
    if content != updated_content:
        # Write the updated content
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Updated message mapping code in {file_path}")
    else:
        print(f"No updates needed or pattern not found in {file_path}")

if __name__ == "__main__":
    update_mapping_code('bot.py')