#!/usr/bin/env python3
"""
Script to update the remaining message mapping code to use memory-efficient function
"""

import re

def update_html_section(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the section around line 2131-2138
    html_pattern = r"""                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            key = \(source_channel_id, source_message_id\)
                            if key not in message_mapping:
                                message_mapping\[key\] = \{\}
                            message_mapping\[key\]\[dest_channel\] = dest_msg_id
                            sent_destinations\[dest_channel\] = dest_msg_id
                            logger\.info\(f"Mapped source message \(\{source_channel_id\}, \{source_message_id\}\) to destination \(\{dest_channel\}, \{dest_msg_id\}\)"\)"""
    
    html_replacement = """                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            # Use memory-efficient mapping function
                            await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                            sent_destinations[dest_channel] = dest_msg_id"""
    
    # Replace HTML section
    updated_content = re.sub(html_pattern, html_replacement, content)
    
    # Find the alternate HTML section around line 2180-2187
    alternate_pattern = r"""                            # Map the message
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                key = \(source_channel_id, source_message_id\)
                                if key not in message_mapping:
                                    message_mapping\[key\] = \{\}
                                message_mapping\[key\]\[dest_channel\] = dest_msg_id
                                sent_destinations\[dest_channel\] = dest_msg_id"""
    
    alternate_replacement = """                            # Map the message
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                # Use memory-efficient mapping function
                                await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                                sent_destinations[dest_channel] = dest_msg_id"""
    
    # Replace alternate HTML section
    updated_content = re.sub(alternate_pattern, alternate_replacement, updated_content)
    
    # Find the regular text section around line 2210-2217
    text_pattern = r"""                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            key = \(source_channel_id, source_message_id\)
                            if key not in message_mapping:
                                message_mapping\[key\] = \{\}
                            message_mapping\[key\]\[dest_channel\] = dest_msg_id
                            sent_destinations\[dest_channel\] = dest_msg_id
                            logger\.info\(f"Mapped source message \(\{source_channel_id\}, \{source_message_id\}\) to destination \(\{dest_channel\}, \{dest_msg_id\}\)"\)"""
    
    text_replacement = """                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            # Use memory-efficient mapping function
                            await add_message_mapping(source_channel_id, source_message_id, dest_channel, dest_msg_id)
                            sent_destinations[dest_channel] = dest_msg_id"""
    
    # Replace text section
    updated_content = re.sub(text_pattern, text_replacement, updated_content)
    
    # Check if we made changes
    if content != updated_content:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(updated_content)
        print(f"Updated remaining mapping sections in {file_path}")
    else:
        print(f"No matching sections found in {file_path} or no changes needed")

if __name__ == "__main__":
    update_html_section('bot.py')