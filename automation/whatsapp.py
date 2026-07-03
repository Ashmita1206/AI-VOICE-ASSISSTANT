"""
WhatsApp Automation
===================

Automates WhatsApp Web using Playwright.
Maintains a persistent browser context to avoid scanning the QR code every time.
"""

import os
import time
import logging
from typing import Any
from execution.schemas import ExecutionResult
from execution.registry import register_tool

logger = logging.getLogger(__name__)

# Note: WhatsApp automation tools require Playwright.
# User must run: pip install playwright && playwright install chromium

def _ensure_playwright():
    """Import and return playwright sync_api."""
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        raise ImportError("Playwright is not installed. Run `pip install playwright`.")

@register_tool("open_whatsapp")
def open_whatsapp(args: dict[str, Any]) -> ExecutionResult:
    """Open WhatsApp Web. We'll use a simple URL open for the non-automated part."""
    try:
        import webbrowser
        webbrowser.open("https://web.whatsapp.com")
        return ExecutionResult(
            success=True,
            tool="open_whatsapp",
            message="Opening WhatsApp Web."
        )
    except Exception as e:
        return ExecutionResult(success=False, tool="open_whatsapp", message=f"Failed to open WhatsApp: {e}")

@register_tool("send_whatsapp_message")
def send_whatsapp_message(args: dict[str, Any]) -> ExecutionResult:
    """Full automation flow: Open WhatsApp, find contact, type and send message."""
    contact = args.get("contact", "")
    message = args.get("message", "")
    
    if not contact or not message:
        return ExecutionResult(success=False, tool="send_whatsapp_message", message="Missing contact or message.")
        
    try:
        sync_playwright = _ensure_playwright()
        user_data_dir = os.path.expanduser("~/.whatsapp_automation_profile")
        
        with sync_playwright() as p:
            # Launch persistent context to save login session
            browser = p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                headless=False,
                args=['--no-sandbox']
            )
            
            page = browser.pages[0] if browser.pages else browser.new_page()
            page.goto("https://web.whatsapp.com")
            
            # Wait for the search box to appear (indicates user is logged in)
            logger.info("Waiting for WhatsApp to load (scan QR if first time)...")
            try:
                search_box = page.wait_for_selector('div[contenteditable="true"][data-tab="3"]', timeout=60000)
            except Exception:
                browser.close()
                return ExecutionResult(
                    success=False, 
                    tool="send_whatsapp_message", 
                    message="Timeout waiting for WhatsApp to load. Please ensure you scan the QR code."
                )
            
            # Search for contact
            search_box.fill(contact)
            page.wait_for_timeout(2000)
            
            # Click the first matching contact in the chat list
            try:
                # Select the title attribute that matches the contact name
                page.click(f'span[title="{contact}"]', timeout=5000)
            except Exception:
                browser.close()
                return ExecutionResult(
                    success=False,
                    tool="send_whatsapp_message",
                    message=f"Could not find contact '{contact}'."
                )
                
            page.wait_for_timeout(1000)
            
            # Find the message input box and type message
            try:
                message_box = page.wait_for_selector('div[contenteditable="true"][data-tab="10"]', timeout=5000)
                message_box.fill(message)
                page.wait_for_timeout(500)
                # Press Enter to send
                message_box.press("Enter")
            except Exception as e:
                browser.close()
                return ExecutionResult(
                    success=False,
                    tool="send_whatsapp_message",
                    message=f"Failed to type or send message: {e}"
                )
            
            page.wait_for_timeout(2000)
            browser.close()
            
            return ExecutionResult(
                success=True,
                tool="send_whatsapp_message",
                message=f"Sent message to {contact}."
            )
            
    except Exception as e:
        logger.error(f"WhatsApp automation failed: {e}")
        return ExecutionResult(success=False, tool="send_whatsapp_message", message=f"Automation failed: {e}")
