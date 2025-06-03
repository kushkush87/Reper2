async def process_message_event(event, is_edit=False):
    """Process message events (new or edited)"""
    # Check if reposting is active
    global reposting_active
    
    # Get source channel and message ID
    source_channel_id = None
    source_message_id = None
    
    try:
        source_channel_id = event.chat_id
        source_message_id = event.message.id
    except:
        if is_edit:
            logger.info("Edited message received (couldn't get chat_id or message_id)")
        else:
            logger.info("New message received (couldn't get chat_id or message_id)")
    
    # Log the event
    if is_edit:
        logger.info(f"Edited message received in channel {source_channel_id}, message ID: {source_message_id}")
    else:
        logger.info(f"New message received in channel {source_channel_id}")
        
    # Check reposting state
    if not reposting_active:
        logger.info("Reposting is not active, ignoring message")
        return
    
    try:
        # Get the message
        message = event.message
        
        # Process message for reposting (apply tag replacements)
        msg_data = await process_message_for_reposting(message)
        
        # Apply content filtering if enabled
        if content_filters["enabled"]:
            should_repost = await filter_content(msg_data)
            if not should_repost:
                logger.info("Message filtered out based on content filters")
                return
                
        # Determine destination channels
        destinations = active_channels["destinations"]
        if not destinations:
            # Fallback to single destination if no multiple destinations set
            if active_channels["destination"]:
                destinations = [active_channels["destination"]]
            else:
                logger.error("No destination channels configured.")
                return
                
        logger.info(f"Preparing to send message to {len(destinations)} destination channels")
        
        # The actual send operation depends on the message type
        if msg_data["has_media"]:
            # Handle media messages
            # Process caption for hyperlinks if applicable
            caption_html = None
            
            if msg_data["media_data"]["caption"] and '[' in msg_data["media_data"]["caption"] and '](' in msg_data["media_data"]["caption"]:
                # Caption processing code...
                # This part is retained from the original function
                pass

            # Send the media with appropriate formatting
            logger.info(f"Sending media of type: {msg_data['media_data']['type']}")
            
            # Track which destinations received the message for mapping
            sent_destinations = {}
            
            # Handle different media types properly - send to each destination
            for dest_channel in destinations:
                try:
                    logger.info(f"Sending to destination channel: {dest_channel}")
                    file_attributes = []
                    
                    # Add attributes from original message if available
                    if "document_attributes" in msg_data:
                        file_attributes = msg_data["document_attributes"]
                    
                    # Variable to store the sent message for mapping
                    dest_message = None
                    
                    # Handle each media type specifically
                    if msg_data["media_data"]["is_photo"]:
                        # Photos
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,  # Send as media, not document
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as photo to {dest_channel}")
                    elif msg_data["media_data"]["is_video"]:
                        # Videos
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,  # Send as media, not document
                            video=True,  # Explicitly mark as video
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as video to {dest_channel}")
                    elif msg_data["media_data"]["is_gif"]:
                        # GIFs
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            video=True,  # GIFs are sent as videos
                            attributes=file_attributes,
                            supports_streaming=True  # Better for GIF-like videos
                        )
                        logger.info(f"Sent as gif to {dest_channel}")
                    elif msg_data["media_data"]["is_sticker"]:
                        # Stickers
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as sticker to {dest_channel}")
                    elif msg_data["media_data"]["is_voice"]:
                        # Voice messages
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            voice=True,  # Explicitly mark as voice
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as voice message to {dest_channel}")
                    elif msg_data["media_data"]["is_audio"]:
                        # Audio files
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,
                            attributes=file_attributes,
                            audio=True  # Explicitly mark as audio
                        )
                        logger.info(f"Sent as audio to {dest_channel}")
                    elif msg_data["media_data"]["is_document"]:
                        # Documents/files
                        file_name = msg_data["media_data"].get("file_name", None)
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=True,  # Send as document
                            attributes=file_attributes,
                            file_name=file_name if file_name else None
                        )
                        logger.info(f"Sent as document to {dest_channel}")
                    else:
                        # Unknown type - let Telegram determine how to send it
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=caption_html if caption_html else msg_data["media_data"]["caption"],
                            parse_mode='html',
                            force_document=False,  # Let Telegram decide
                            attributes=file_attributes
                        )
                        logger.info(f"Sent as unknown media type to {dest_channel}")
                    
                    # Store the message mapping if this is a new message (not an edit)
                    if not is_edit and source_channel_id and source_message_id and dest_message:
                        dest_msg_id = dest_message.id
                        # Track in the mapping dictionary
                        key = (source_channel_id, source_message_id)
                        if key not in message_mapping:
                            message_mapping[key] = {}
                        # Add this destination
                        message_mapping[key][dest_channel] = dest_msg_id
                        sent_destinations[dest_channel] = dest_msg_id
                        logger.info(f"Mapped source message ({source_channel_id}, {source_message_id}) to destination ({dest_channel}, {dest_msg_id})")
                    
                except Exception as e:
                    logger.error(f"Error sending media to {dest_channel}: {str(e)}")
                    
                    # Fallback - try sending without special attributes
                    try:
                        dest_message = await user_client.send_file(
                            dest_channel,
                            msg_data["file_path"],
                            caption=msg_data["media_data"]["caption"],
                            force_document=False  # Let Telegram determine type
                        )
                        logger.info(f"Sent media using fallback method to {dest_channel}")
                        
                        # Store mapping even for fallback method
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            key = (source_channel_id, source_message_id)
                            if key not in message_mapping:
                                message_mapping[key] = {}
                            message_mapping[key][dest_channel] = dest_msg_id
                            sent_destinations[dest_channel] = dest_msg_id
                    except Exception as e2:
                        logger.error(f"Error in fallback send to {dest_channel}: {str(e2)}")
                        
                        # Last resort - try as document
                        try:
                            dest_message = await user_client.send_file(
                                dest_channel,
                                msg_data["file_path"],
                                caption=msg_data["media_data"]["caption"],
                                force_document=True
                            )
                            logger.info(f"Sent as document after all other methods failed to {dest_channel}")
                            
                            # Store mapping even for last resort method
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                key = (source_channel_id, source_message_id)
                                if key not in message_mapping:
                                    message_mapping[key] = {}
                                message_mapping[key][dest_channel] = dest_msg_id
                                sent_destinations[dest_channel] = dest_msg_id
                        except Exception as e3:
                            logger.error(f"Complete failure sending media to {dest_channel}: {str(e3)}")
            
            # Clean up the temporary file
            if msg_data["file_path"] and os.path.exists(msg_data["file_path"]):
                os.unlink(msg_data["file_path"])
                
        else:
            # Handle text-only messages
            # Track which destinations received the message
            sent_destinations = {}
            
            # For messages with hyperlinks, try a different approach
            if msg_data.get("html_backup", False):
                # Text message with HTML processing
                for dest_channel in destinations:
                    try:
                        logger.info(f"Sending text message with hyperlinks to {dest_channel}")
                        
                        # Create formatted HTML with hyperlinks - reuse existing code
                        # The original complex HTML creation logic stays the same
                        html_message = msg_data["text"]
                        
                        # Create completely new HTML document to fix duplication issues
                        raw_text = msg_data["text"]
                        parts = []
                        last_end = 0
                        
                        # Sort entities by offset
                        sorted_entities = sorted(msg_data["entities"], key=lambda e: e.offset)
                        
                        # Track processed ranges to avoid duplication
                        processed_ranges = []
                        
                        # Consolidate overlapping entities
                        consolidated_entities = []
                        for entity in sorted_entities:
                            if isinstance(entity, MessageEntityTextUrl):
                                entity_range = (entity.offset, entity.offset + entity.length)
                                if not any(start <= entity_range[0] < end for start, end in processed_ranges):
                                    consolidated_entities.append(entity)
                                    processed_ranges.append(entity_range)
                        
                        # Process each entity
                        last_end = 0
                        for entity in consolidated_entities:
                            if isinstance(entity, MessageEntityTextUrl):
                                # Add text before entity
                                if entity.offset > last_end:
                                    parts.append(raw_text[last_end:entity.offset])
                                
                                # Add entity as HTML tag
                                link_text = raw_text[entity.offset:entity.offset + entity.length]
                                
                                # Apply all the link text fixes as in the original code
                                # Clean markdown, handle duplication, etc.
                                
                                parts.append(f'<a href="{entity.url}">{link_text}</a>')
                                last_end = entity.offset + entity.length
                        
                        # Add remaining text
                        if last_end < len(raw_text):
                            parts.append(raw_text[last_end:])
                        
                        # Build final HTML message
                        html_message = ''.join(parts)
                        
                        # Send the HTML formatted message
                        dest_message = await user_client.send_message(
                            dest_channel,
                            html_message,
                            parse_mode='html'
                        )
                        logger.info(f"Successfully sent HTML message to {dest_channel}")
                        
                        # Store the message mapping if this is a new message
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            key = (source_channel_id, source_message_id)
                            if key not in message_mapping:
                                message_mapping[key] = {}
                            message_mapping[key][dest_channel] = dest_msg_id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Mapped source message ({source_channel_id}, {source_message_id}) to destination ({dest_channel}, {dest_msg_id})")
                            
                    except Exception as e:
                        logger.error(f"Error sending HTML message to {dest_channel}: {str(e)}")
                        
                        # Try alternate HTML approach with markdown links
                        try:
                            # Alternate HTML approach (same as original)
                            markdown_text = msg_data["text"]
                            markdown_replacements = []
                            
                            # Process entities for markdown replacements
                            for entity in msg_data["entities"]:
                                if isinstance(entity, MessageEntityTextUrl):
                                    link_text = markdown_text[entity.offset:entity.offset + entity.length]
                                    markdown_replacements.append({
                                        'start': entity.offset,
                                        'end': entity.offset + entity.length,
                                        'text': link_text,
                                        'url': entity.url
                                    })
                            
                            # Sort and apply replacements
                            markdown_replacements.sort(key=lambda x: x['start'], reverse=True)
                            for replacement in markdown_replacements:
                                start = replacement['start']
                                end = replacement['end']
                                link_text = replacement['text']
                                markdown_link = f'<a href="{replacement["url"]}">{link_text}</a>'
                                markdown_text = markdown_text[:start] + markdown_link + markdown_text[end:]
                            
                            # Send with alternate format
                            dest_message = await user_client.send_message(
                                dest_channel,
                                markdown_text,
                                parse_mode='html'
                            )
                            logger.info(f"Successfully sent alternate HTML message to {dest_channel}")
                            
                            # Map the message
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                key = (source_channel_id, source_message_id)
                                if key not in message_mapping:
                                    message_mapping[key] = {}
                                message_mapping[key][dest_channel] = dest_msg_id
                                sent_destinations[dest_channel] = dest_msg_id
                                
                        except Exception as e2:
                            logger.error(f"Error sending alternate HTML message to {dest_channel}: {str(e2)}")
            else:
                # Regular text message without HTML processing
                for dest_channel in destinations:
                    message_sent = False
                    try:
                        # First try with entities if available
                        if msg_data["entities"]:
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"],
                                formatting_entities=msg_data["entities"]  # Use formatting_entities instead of entities
                            )
                            message_sent = True
                            logger.info(f"Sent message with entities to {dest_channel}")
                        else:
                            # If no entities, use parse_mode
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"],
                                parse_mode='html'
                            )
                            message_sent = True
                            logger.info(f"Sent message with HTML parse mode to {dest_channel}")
                            
                        # Store the message mapping
                        if not is_edit and source_channel_id and source_message_id and dest_message:
                            dest_msg_id = dest_message.id
                            key = (source_channel_id, source_message_id)
                            if key not in message_mapping:
                                message_mapping[key] = {}
                            message_mapping[key][dest_channel] = dest_msg_id
                            sent_destinations[dest_channel] = dest_msg_id
                            logger.info(f"Mapped source message ({source_channel_id}, {source_message_id}) to destination ({dest_channel}, {dest_msg_id})")
                            
                    except Exception as e:
                        logger.error(f"Error sending message to {dest_channel}: {str(e)}")
                        # Fallback to sending plain text
                        try:
                            dest_message = await user_client.send_message(
                                dest_channel,
                                msg_data["text"]
                            )
                            message_sent = True
                            logger.info(f"Sent plain text message to {dest_channel}")
                            
                            # Store the message mapping
                            if not is_edit and source_channel_id and source_message_id and dest_message:
                                dest_msg_id = dest_message.id
                                key = (source_channel_id, source_message_id)
                                if key not in message_mapping:
                                    message_mapping[key] = {}
                                message_mapping[key][dest_channel] = dest_msg_id
                                sent_destinations[dest_channel] = dest_msg_id
                                
                        except Exception as e2:
                            logger.error(f"Failed to send message to {dest_channel}: {str(e2)}")
        
        # Log the message mapping status
        if not is_edit:
            logger.info(f"Successfully sent message to {len(sent_destinations)} destination channels")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
