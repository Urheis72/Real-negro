import asyncio
import os
import re
import requests
import logging
from telethon import TelegramClient, events
from telethon.tl.types import UpdateNewMessage, MessageActionChatAddUser

# --- CONFIG ---
# Target Result Group ID: 7748071327
RESULT_GROUP_ID = 7748071327 

async def _on_result_message(self, event):
    """
    Listener for the result group (7748071327)
    """
    if not self.pending_request or self.pending_request.done():
        return

    logger.info(f"📩 New message in result group. Checking for buttons...")

    try:
        # 1. Look for the 'Abrir resultado' button shown in Screenshot_20251229-162959_1.jpg
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if "Abrir resultado" in btn.text:
                        logger.info("🔘 'Abrir resultado' button found. Clicking...")
                        
                        # In Telethon, clicking a button with a link returns the link directly
                        # as shown in the popup in Screenshot_20251229-163039.jpg
                        result = await event.message.click(btn)
                        
                        final_url = None
                        if isinstance(result, str):
                            final_url = result
                        elif hasattr(btn, 'url'):
                            final_url = btn.url

                        if final_url:
                            logger.info(f"🔗 URL captured from popup: {final_url}")
                            # 2. Open the link and capture the final data
                            extracted_data = self._scrape_content(final_url)
                            self.pending_request.set_result(extracted_data)
                        else:
                            logger.error("❌ Failed to resolve URL from button click.")
                        return

        # 3. Fallback: If result says "disponível no privado" (Screenshot_20251229-164846_1.jpg)
        if "disponível no privado" in event.message.message:
            logger.warning("⚠️ Bot redirected result to private. Ensure you are monitoring DMs too.")

    except Exception as e:
        logger.error(f"❌ Error extracting result: {e}")
        if not self.pending_request.done():
            self.pending_request.set_exception(e)

def _scrape_content(self, url):
    """
    Opens the api.fdxapis.us link (from Screenshot_20251229-163039.jpg) 
    and returns the result.
    """
    try:
        logger.info(f"🌍 Fetching result data from external API link...")
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        # Following redirects is important for these temporary result links
        response = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        
        if response.status_code == 200:
            # You might need to parse specific HTML tags here depending on the site's structure
            return response.text[:3000] # Return result to front-end
        else:
            return f"Erro ao acessar link do resultado (HTTP {response.status_code})"
    except Exception as e:
        return f"Falha na extração externa: {str(e)}"
