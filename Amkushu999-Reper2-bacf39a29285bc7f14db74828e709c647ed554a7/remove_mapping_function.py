#!/usr/bin/env python3
"""
Script to remove all instances of mapping references in the bot.py file.
This implements a no-storage approach to handling messages as requested by the user.
"""

import re

def update_fallback_mapping_code():
    """Update the fallback mapping code to not store mappings"""
    with open('bot.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace media fallback mapping code
    fallback_pattern = r"""                        # Store mapping even for fallback method
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message\.id
                            await add_message_mapping\(source_channel_id, source_message_id, dest_channel, dest_msg_id\)
                            sent_destinations\[dest_channel\] = dest_msg_id"""
    
    fallback_replacement = """                        # No message mapping stored (per user requirements)
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")"""
    
    # Replace all instances of the pattern
    updated_content = re.sub(fallback_pattern, fallback_replacement, content)
    
    # Replace HTML message mapping code
    html_pattern = r"""                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message\.id
                            # Use memory-efficient mapping function
                            await add_message_mapping\(source_channel_id, source_message_id, dest_channel, dest_msg_id\)
                            sent_destinations\[dest_channel\] = dest_msg_id
                            logger\.info\(f"Mapped source message \(\{source_channel_id\}, \{source_message_id\}\) to destination \(\{dest_channel\}, \{dest_msg_id\}\)"\)"""
    
    html_replacement = """                        # No message mapping stored (per user requirements)
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")"""
    
    # Replace all instances of the pattern
    updated_content = re.sub(html_pattern, html_replacement, updated_content)
    
    # Replace mapping code
    map_pattern = r"""                            # Map the message
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message\.id
                                # Use memory-efficient mapping function
                                await add_message_mapping\(source_channel_id, source_message_id, dest_channel, dest_msg_id\)
                                sent_destinations\[dest_channel\] = dest_msg_id"""
    
    map_replacement = """                            # No message mapping stored (per user requirements)
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                sent_destinations[dest_channel] = dest_msg_id
                                logger.info(f"Message from ({source_channel_id}, {source_message_id}) reposted to {dest_channel}")"""
    
    # Replace all instances of the pattern
    updated_content = re.sub(map_pattern, map_replacement, updated_content)
    
    # Remove all check references to message_mapping
    updated_content = updated_content.replace("if key in message_mapping and message_mapping[key]:", "if False:  # No message mappings are stored")
    updated_content = updated_content.replace("message_mapping[key].pop(dest_channel, None)", "pass  # No message mappings to modify")
    
    # Replace message_mapping declarations
    updated_content = updated_content.replace("message_mapping = {}", "# No message mappings - this is intentionally left empty")
    
    # Write the updated content back to the file
    with open('bot.py', 'w', encoding='utf-8') as f:
        f.write(updated_content)
    
    print("Updated bot.py to remove all message mapping references.")

if __name__ == "__main__":
    update_fallback_mapping_code()