"""
Outlook integration tool for nanobot.

Provides tools to:
- Find emails in Outlook based on various criteria (date, folder, sender)
- Extract attachments from emails
- Send emails with analysis reports

Requires:
- pywin32: pip install pywin32
- Outlook application installed on Windows
"""

import os
import tempfile
from datetime import datetime
from typing import Any
import asyncio

from loguru import logger

from nanobot.agent.tools.base import Tool, RiskTier


# Outlook item class constants
OL_MAIL_ITEM = 43  # MailItem class

# Supported document attachment types (common office files)
SUPPORTED_ATTACHMENT_TYPES = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.txt', '.csv', '.rtf', '.odt', '.ods', '.odp'
}

# Image types to ignore (often used in signatures)
IGNORED_ATTACHMENT_TYPES = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.ico', '.webp'
}


class OutlookTool(Tool):
    """
    Tool for interacting with Microsoft Outlook.
    
    Allows finding emails, extracting attachments, and sending reports.
    Supports nested folders under Inbox (e.g., "Inbox/Reporting").
    Requires Outlook application to be running on Windows.
    
    State Management:
    - Tracks current folder and search results to ensure get_attachment 
      can access previously found emails.
    - R12: State (_last_search_results, _current_folder_name) is per-instance.
      Each AgentLoop creates its own OutlookTool via setup_all_tools(),
      so concurrent agent sessions hold independent state. If the tool
      were ever promoted to a process-wide singleton, state should be
      keyed by session_key instead.
    """
    
    def __init__(self):
        self._current_folder_name = "inbox"
        self._last_search_results = []
        self._lock = asyncio.Lock()  # Phase 31 Retro: protect COM shared state
    
    @property
    def name(self) -> str:
        return "outlook"
    
    @property
    def description(self) -> str:
        return """Microsoft Outlook integration tool.
Allows you to:
- Find emails by subject, sender, recipient, date, or folder
  - Supports nested folders like "Inbox/Reporting"
  - Supports "sent" folder for Sent Items
- Read full email body with read_email action
- Extract attachments from found emails (filters out images, keeps documents only)
- Send emails with attachments

IMPORTANT (执行力要求):
1. When user says "analyze emails" or "analyze attachments", you MUST:
   a) Call find_emails to get today's emails
   b) Call get_all_attachments to extract ALL attachments (don't ask user!)
   c) Analyze each attachment
   d) Generate report
   e) Send email if user requested
2. DO NOT ask "do you want me to continue?" after each step
3. Just EXECUTE the full workflow automatically
4. If user says "send to my email", MUST call send_email
5. To search sent emails, use folder="sent"
6. To find emails sent TO someone, use to_email parameter
7. To read full email body after find_emails, use read_email action

Note: Requires Outlook application to be running on Windows."""
    
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["find_emails", "read_email", "get_attachment", "get_all_attachments", "send_email", "list_folders"],
                    "description": "The action to perform. Use read_email to get the full body of a previously found email."
                },
                "criteria": {
                    "type": "object",
                    "description": "Search criteria (for find_emails action)",
                    "properties": {
                        "subject_contains": {"type": "string"},
                        "from_email": {"type": "string", "description": "Filter by sender email address (partial match)"},
                        "to_email": {"type": "string", "description": "Filter by recipient email address (partial match, for sent folder)"},
                        "folder": {"type": "string", "description": "Folder to search. 'inbox' (default), 'sent' for Sent Items, or nested path like 'inbox/reporting'"},
                        "received_after": {"type": "string"},
                        "received_before": {"type": "string"},
                        "has_attachments": {"type": "boolean", "default": False},
                        "max_results": {"type": "integer", "default": 10}
                    }
                },
                "email_index": {"type": "integer"},
                "attachment_index": {"type": "integer", "default": 0},
                "save_directory": {"type": "string"},
                "recipient": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "attachment_paths": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["action"]
        }
    
    def get_risk_tier(self, args: dict[str, Any]) -> RiskTier:
        action = args.get("action", "find_emails")
        if action in ["send_email"]:
            return RiskTier.MUTATE_EXTERNAL
        elif action in ["delete_email"]:
            return RiskTier.DESTRUCTIVE
        return RiskTier.READ_ONLY
    
    async def execute(self, **kwargs: Any) -> str:
        async with self._lock:
            return await self._execute_impl(**kwargs)

    async def _execute_impl(self, **kwargs: Any) -> str:
        action = kwargs.get("action", "find_emails")
        
        try:
            if action == "find_emails":
                return await self._find_emails(kwargs.get("criteria", {}))
            elif action == "read_email":
                return await self._read_email(
                    kwargs.get("email_index", 0)
                )
            elif action == "get_attachment":
                return await self._get_attachment(
                    kwargs.get("email_index", 0),
                    kwargs.get("attachment_index", 0),
                    kwargs.get("save_directory")
                )
            elif action == "get_all_attachments":
                return await self._get_all_attachments(
                    kwargs.get("email_index", 0),
                    kwargs.get("save_directory")
                )
            elif action == "send_email":
                return await self._send_email(
                    kwargs.get("recipient", ""),
                    kwargs.get("subject", ""),
                    kwargs.get("body", ""),
                    kwargs.get("attachment_paths", [])
                )
            elif action == "list_folders":
                return await self._list_folders()
            else:
                return f"Unknown action: {action}"
        except Exception as e:
            logger.error(f"Outlook tool error: {e}")
            return f"Error: {str(e)}"
    
    def _get_outlook():
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()
            outlook_app = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook_app.GetNamespace("MAPI")
            return outlook_app, namespace
        except Exception as e:
            raise Exception(f"Failed to connect to Outlook: {e}")
    
    def _get_folder(outlook_app, namespace, folder_path: str):
        if not folder_path:
            folder_path = "inbox"
        
        folder_path = folder_path.replace('\\', '/').lower()
        parts = [p.strip() for p in folder_path.split('/') if p.strip()]
        
        if not parts:
            return namespace.GetDefaultFolder(6)
        
        if parts[0].lower() == 'inbox':
            current = namespace.GetDefaultFolder(6)
            parts = parts[1:]
        elif parts[0].lower() in ('sent', 'sent items', 'sentitems', 'sent_items'):
            current = namespace.GetDefaultFolder(5)  # olFolderSentMail
            parts = parts[1:]
        else:
            current = None
            for folder in namespace.Folders:
                if folder.Name.lower() == parts[0].lower():
                    current = folder
                    break
            
            if current is None:
                raise Exception(f"Folder not found: {parts[0]}")
            parts = parts[1:]
        
        for part in parts:
            found = False
            for folder in current.Folders:
                if folder.Name.lower() == part.lower():
                    current = folder
                    found = True
                    break
            
            if not found:
                raise Exception(f"Subfolder not found: {part}")
        
        return current
    
    def _is_mail_item(item) -> bool:
        try:
            return item.Class == OL_MAIL_ITEM
        except Exception:
            return False
    
    def _get_all_attachment_info(item) -> list[dict]:
        """Get information about all document attachments. Uses 0-based indexing."""
        attachments_info = []
        try:
            attachments = item.Attachments
            if attachments is not None:
                count = attachments.Count
                logger.debug(f"Attachment count: {count}")
                
                # Use 0-based indexing for Outlook Attachments!
                for idx in range(count):
                    try:
                        att = attachments[idx]  # 0-based!
                        filename = att.FileName
                        ext = os.path.splitext(filename)[1].lower()
                        
                        # Skip images
                        if ext in IGNORED_ATTACHMENT_TYPES:
                            continue
                        
                        # Only include supported document types
                        if ext in SUPPORTED_ATTACHMENT_TYPES:
                            attachments_info.append({
                                "outlook_index": idx,  # 0-based!
                                "filtered_index": len(attachments_info),
                                "filename": filename,
                                "extension": ext,
                                "type": OutlookTool._get_file_type_name(ext)
                            })
                    except Exception as e:
                        logger.debug(f"Error processing attachment {idx}: {e}")
                        pass
                    # Release COM object explicitly
                    try:
                        del att
                    except Exception:
                        pass
        except Exception as e:
            logger.debug(f"Error getting attachments: {e}")
            pass
        return attachments_info
    
    @staticmethod
    def _get_file_type_name(ext: str) -> str:
        type_map = {
            '.pdf': 'PDF Document',
            '.doc': 'Word Document',
            '.docx': 'Word Document',
            '.xls': 'Excel Spreadsheet',
            '.xlsx': 'Excel Spreadsheet',
            '.ppt': 'PowerPoint Presentation',
            '.pptx': 'PowerPoint Presentation',
            '.txt': 'Text File',
            '.csv': 'CSV File',
        }
        return type_map.get(ext, 'Document')
    
    @staticmethod
    def _safe_get_property(item, prop_name: str, default=None):
        try:
            return getattr(item, prop_name, default)
        except Exception:
            return default
    
    @staticmethod
    def _normalize_datetime(dt):
        if dt is None:
            return None
        if hasattr(dt, 'tzinfo') and dt.tzinfo is not None:
            try:
                return dt.replace(tzinfo=None)
            except Exception:
                return dt
        return dt
    
    async def _find_emails(self, criteria: dict) -> str:
        def _sync_find():
            import pythoncom
            outlook, namespace = None, None
            folder_name = criteria.get("folder", "inbox")
            try:
                outlook, namespace = OutlookTool._get_outlook()
                
                folder = OutlookTool._get_folder(outlook, namespace, folder_name)
                
                items = folder.Items
                items.Sort("[ReceivedTime]", True)
                
                max_results = criteria.get("max_results", 50)
                has_attachments = criteria.get("has_attachments", False)
                
                has_date_filter = bool(criteria.get("received_after") or criteria.get("received_before"))
                if not has_date_filter:
                    today = datetime.now().strftime("%Y-%m-%d")
                    criteria["received_after"] = today
                
                results = []
                count = 0
                max_check = min(100, items.Count)
                
                for i in range(max_check):
                    item = None
                    try:
                        item = items[i + 1]
                        
                        if not OutlookTool._is_mail_item(item):
                            continue
                        
                        received_time = OutlookTool._safe_get_property(item, 'ReceivedTime')
                        if received_time is None:
                            continue
                        
                        received_time_normalized = OutlookTool._normalize_datetime(received_time)
                        
                        after_date = criteria.get("received_after")
                        if after_date:
                            after = datetime.strptime(after_date, "%Y-%m-%d")
                            if received_time_normalized and received_time_normalized < after:
                                continue
                        
                        before_date = criteria.get("received_before")
                        if before_date:
                            before = datetime.strptime(before_date, "%Y-%m-%d")
                            if received_time_normalized and received_time_normalized > before:
                                continue
        
                        subject = OutlookTool._safe_get_property(item, 'Subject', '') or ''
                        
                        subject_keyword = criteria.get("subject_contains")
                        if subject_keyword:
                            if subject_keyword.lower() not in subject.lower():
                                continue
                        
                        sender = OutlookTool._safe_get_property(item, 'SenderEmailAddress', '') or ''
                        
                        from_keyword = criteria.get("from_email")
                        if from_keyword:
                            if from_keyword.lower() not in sender.lower():
                                continue
                        
                        to_keyword = criteria.get("to_email")
                        if to_keyword:
                            recipients = OutlookTool._safe_get_property(item, 'To', '') or ''
                            if to_keyword.lower() not in recipients.lower():
                                continue
                        
                        attachment_info = OutlookTool._get_all_attachment_info(item)
                        document_count = len(attachment_info)
                        
                        if has_attachments and document_count == 0:
                            continue
                        
                        if attachment_info:
                            attachment_desc = ", ".join([f"{a['filename']} ({a['type']})" for a in attachment_info])
                            attachment_info_str = f" [{document_count} docs: {attachment_desc}]"
                        else:
                            attachment_info_str = " [No document attachments]"
                        
                        body = OutlookTool._safe_get_property(item, 'Body', '') or ''
                        
                        result_entry = {
                            "index": count,
                            "items_index": i + 1,
                            "folder": folder_name,
                            "subject": subject,
                            "sender": sender,
                            "received": str(received_time),
                            "attachments": attachment_info_str,
                            "attachment_details": attachment_info,
                            "document_count": document_count,
                            "body_preview": body[:200] if body else ''
                        }
                        results.append(result_entry)
                        count += 1
                        
                        if count >= max_results:
                            break
                            
                    except Exception as e:
                        logger.debug(f"Error processing email {i}: {e}")
                        continue
                    finally:
                        if item:
                            try:
                                del item
                            except Exception:
                                pass
                
                return results, folder_name
            except Exception as e:
                logger.error(f"Error in find sync thread: {e}")
                return [], folder_name
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                pythoncom.CoUninitialize()

        results, folder_name = await asyncio.to_thread(_sync_find)
        
        self._current_folder_name = folder_name
        self._last_search_results = results
        
        if not results:
            return "No emails found matching the criteria."
        
        output = [f"Found {len(results)} email(s) in folder '{folder_name}':\n"]
        output.append("Note: Only document attachments (PDF, Word, Excel, PowerPoint) are shown. Images are ignored.\n")
        
        for r in results:
            preview = r['body_preview'][:100] if r['body_preview'] else ''
            output.append(f"""---
[{r['index']}] Subject: {r['subject']}
From: {r['sender']}
Received: {r['received']}
Attachments:{r['attachments']}
Preview: {preview}...""")
        
        output.append(f"\nTo get attachments, use: email_index=X")
        
        return "\n".join(output)
    
    async def _get_attachment(self, email_index: int, attachment_index: int, save_directory: str = None) -> str:
        if not self._last_search_results:
            return "Error: No search results found."
        
        if email_index < 0 or email_index >= len(self._last_search_results):
            return f"Error: Invalid email_index."
        
        result_info = self._last_search_results[email_index]
        folder_name = result_info["folder"]
        items_index = result_info["items_index"]
        attachment_details = result_info.get("attachment_details", [])
        
        if not attachment_details:
            return "This email has no document attachments."
        
        if attachment_index < 0 or attachment_index >= len(attachment_details):
            return f"Error: Invalid attachment_index."
        
        att_info = attachment_details[attachment_index]
        outlook_index = att_info["outlook_index"]  # 0-based!
        
        if save_directory is None:
            save_directory = tempfile.gettempdir()
        elif not os.path.exists(save_directory):
            return f"Error: Directory does not exist."

        def _sync_get_attachment():
            import pythoncom
            outlook, namespace = None, None
            try:
                outlook, namespace = OutlookTool._get_outlook()
                folder = OutlookTool._get_folder(outlook, namespace, folder_name)
                items = folder.Items
                items.Sort("[ReceivedTime]", True)
                
                if items_index > items.Count:
                    return "Error: Email no longer exists."
                
                item = items[items_index]
                
                if not OutlookTool._is_mail_item(item):
                    return "Error: Not a valid email."
                
                try:
                    attachment = item.Attachments[outlook_index]  # 0-based!
                    filename = attachment.FileName
                except Exception as e:
                    return f"Error: Could not access attachment: {e}"
                
                save_path = os.path.join(save_directory, filename)
                
                base, ext = os.path.splitext(save_path)
                counter = 1
                while os.path.exists(save_path):
                    save_path = f"{base}_{counter}{ext}"
                    counter += 1
                
                attachment.SaveAsFile(save_path)
                
                del attachment
                del item
                
                return f"Attachment saved to: {save_path}\nFilename: {filename}\nSize: {os.path.getsize(save_path)} bytes"
            except Exception as e:
                return f"Error connecting to Outlook or obtaining attachment: {e}"
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                pythoncom.CoUninitialize()

        res = await asyncio.to_thread(_sync_get_attachment)
        return res if res is not None else "Error: Attachment thread returned None"
    
    async def _get_all_attachments(self, email_index: int, save_directory: str = None) -> str:
        if not self._last_search_results:
            return "Error: No search results found."
        
        if email_index < 0 or email_index >= len(self._last_search_results):
            return "Error: Invalid email_index."
        
        result_info = self._last_search_results[email_index]
        folder_name = result_info["folder"]
        items_index = result_info["items_index"]
        attachment_details = result_info.get("attachment_details", [])
        
        if not attachment_details:
            return "This email has no document attachments."
        
        if save_directory is None:
            save_directory = tempfile.gettempdir()
        elif not os.path.exists(save_directory):
            return "Error: Directory does not exist."

        def _sync_get_all_attachments():
            import pythoncom
            outlook, namespace = None, None
            try:
                outlook, namespace = OutlookTool._get_outlook()
                folder = OutlookTool._get_folder(outlook, namespace, folder_name)
                items = folder.Items
                items.Sort("[ReceivedTime]", True)
                
                if items_index > items.Count:
                    return "Error: Email no longer exists."
                
                item = items[items_index]
                
                if not OutlookTool._is_mail_item(item):
                    return "Error: Not a valid email."
                
                saved_files = []
                errors = []
                
                for att_info in attachment_details:
                    outlook_index = att_info["outlook_index"]  # 0-based!
                    attachment = None
                    try:
                        attachment = item.Attachments[outlook_index]
                        filename = attachment.FileName
                        
                        save_path = os.path.join(save_directory, filename)
                        
                        base, ext = os.path.splitext(save_path)
                        counter = 1
                        while os.path.exists(save_path):
                            save_path = f"{base}_{counter}{ext}"
                            counter += 1
                        
                        attachment.SaveAsFile(save_path)
                        saved_files.append(f"{filename} -> {save_path}")
                    except Exception as e:
                        errors.append(f"{att_info['filename']}: {e}")
                    finally:
                        if attachment:
                            try:
                                del attachment
                            except Exception:
                                pass
                
                del item
                
                output = [f"Saved {len(saved_files)} document attachment(s):\n"]
                for sf in saved_files:
                    output.append(f"  - {sf}")
                
                if errors:
                    output.append(f"\nErrors ({len(errors)}):")
                    for err in errors:
                        output.append(f"  - {err}")
                
                return "\n".join(output)
            except Exception as e:
                return f"Error executing all attachments task: {e}"
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                pythoncom.CoUninitialize()

        res = await asyncio.to_thread(_sync_get_all_attachments)
        return res if res is not None else "Error: Get all threads returned None"
    
    async def _send_email(self, recipient: str, subject: str, body: str, attachment_paths: list[str]) -> str:
        if not recipient or not recipient.strip():
            return "Error: recipient is empty. Please provide a valid email address."

        # Basic email format validation
        clean_recipient = recipient.strip()
        if " " in clean_recipient and "@" not in clean_recipient:
            return f"Error: '{clean_recipient}' does not look like a valid email address."

        def _sync_send_email():
            import pythoncom
            outlook, namespace = None, None
            try:
                pythoncom.CoInitialize()
                outlook, namespace = OutlookTool._get_outlook()
                
                mail = outlook.CreateItem(0)
                # L14: Robust external email handling with PropertyAccessor fallback.
                # Previous fixes (L4, L9) failed because:
                #  - L4: just standardized error strings
                #  - L9: used Recipients.Add + Resolve, but Send() still threw
                #         "Outlook does not recognize one or more names"
                # Root cause: Exchange GAL resolution rejects unknown external addresses.
                # Fix: Force SMTP address type via PropertyAccessor, then ResolveAll.
                PR_SMTP_ADDRESS = "http://schemas.microsoft.com/mapi/proptag/0x39FE001E"
                recip = mail.Recipients.Add(clean_recipient)
                recip.Type = 1  # olTo
                try:
                    recip.PropertyAccessor.SetProperty(PR_SMTP_ADDRESS, clean_recipient)
                except Exception as pa_err:
                    logger.debug(f"PropertyAccessor.SetProperty failed (non-fatal): {pa_err}")
                
                # ResolveAll is more reliable than individual Resolve
                resolved = mail.Recipients.ResolveAll()
                if not resolved:
                    logger.debug(f"Recipients.ResolveAll() returned False for '{clean_recipient}' (may still work for SMTP)")
                
                mail.Subject = subject
                mail.Body = body
                
                for path in attachment_paths:
                    if os.path.exists(path):
                        mail.Attachments.Add(path)
                
                try:
                    mail.Send()
                    del mail
                    logger.info(f"Outlook: email sent successfully to {clean_recipient}")
                    return f"Email sent successfully to {clean_recipient}"
                except Exception as send_err:
                    logger.warning(f"Outlook Send() failed with PropertyAccessor approach: {send_err}")
                    # Fallback: create a fresh mail item using mail.To directly
                    try:
                        del mail
                    except Exception:
                        pass
                    
                    logger.info("Attempting fallback: mail.To direct assignment")
                    mail2 = outlook.CreateItem(0)
                    mail2.To = clean_recipient
                    mail2.Subject = subject
                    mail2.Body = body
                    for path in attachment_paths:
                        if os.path.exists(path):
                            mail2.Attachments.Add(path)
                    mail2.Send()
                    del mail2
                    logger.info(f"Outlook: email sent via fallback to {clean_recipient}")
                    return f"Email sent successfully to {clean_recipient} (via fallback)"

            except Exception as e:
                logger.error(f"Outlook send_email failed: {e}")
                return f"Error: Failed to send email to {clean_recipient}: {e}"
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        
        res = await asyncio.to_thread(_sync_send_email)
        return res if res is not None else "Error: Send thread returned None"
    
    async def _list_folders(self) -> str:
        def _sync_list_folders():
            import pythoncom
            outlook, namespace = None, None
            try:
                outlook, namespace = OutlookTool._get_outlook()
                
                def get_all_folders(folder, prefix=""):
                    result = [(f"{prefix}{folder.Name}", folder.Items.Count)]
                    try:
                        for subfolder in folder.Folders:
                            result.extend(get_all_folders(subfolder, f"{prefix}{folder.Name}/"))
                    except Exception:
                        pass
                    return result
                
                inbox = namespace.GetDefaultFolder(6)
                all_folders = get_all_folders(inbox)
                
                output = ["Email Folders:\n"]
                for name, count in all_folders:
                    output.append(f"- {name} ({count} items)")
                
                return "\n".join(output)
            except Exception as e:
                return f"Error listing folders: {e}"
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                pythoncom.CoUninitialize()

        res = await asyncio.to_thread(_sync_list_folders)
        return res if res is not None else "Error: List folders thread returned None"
    
    async def _read_email(self, email_index: int) -> str:
        """Return the full body and metadata of a previously found email."""
        if not self._last_search_results:
            return "Error: No search results. Run find_emails first."
        if email_index < 0 or email_index >= len(self._last_search_results):
            return f"Error: Invalid email_index. Valid range: 0-{len(self._last_search_results)-1}"
        
        result_info = self._last_search_results[email_index]
        folder_name = result_info.get("folder", "inbox")
        items_index = result_info.get("items_index", 1)

        def _sync_read_email():
            import pythoncom
            outlook, namespace = None, None
            try:
                outlook, namespace = OutlookTool._get_outlook()
                folder = OutlookTool._get_folder(outlook, namespace, folder_name)
                items = folder.Items
                items.Sort("[ReceivedTime]", True)
                
                if items_index > items.Count:
                    return "Error: Email no longer exists in folder."
                
                item = items[items_index]
                
                if not OutlookTool._is_mail_item(item):
                    return "Error: Not a valid email item."
                
                subject = OutlookTool._safe_get_property(item, 'Subject', '') or ''
                sender = OutlookTool._safe_get_property(item, 'SenderEmailAddress', '') or ''
                received = str(OutlookTool._safe_get_property(item, 'ReceivedTime', ''))
                to = OutlookTool._safe_get_property(item, 'To', '') or ''
                cc = OutlookTool._safe_get_property(item, 'CC', '') or ''
                body = OutlookTool._safe_get_property(item, 'Body', '') or ''
                
                del item

                output = f"""Subject: {subject}
From: {sender}
To: {to}
CC: {cc}
Received: {received}

--- Email Body ---
{body}"""
                return output
            except Exception as e:
                logger.error(f"Error reading email: {e}")
                return f"Error reading email: {str(e)}"
            finally:
                if outlook:
                    del outlook
                if namespace:
                    del namespace
                pythoncom.CoUninitialize()
        
        res = await asyncio.to_thread(_sync_read_email)
        return res if res is not None else "Error: Thread returned None"
    
    def reset_state(self):
        self._current_folder_name = "inbox"
        self._last_search_results = []
