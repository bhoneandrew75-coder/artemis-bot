import os
import re
import asyncio
import logging
from datetime import datetime
from typing import Dict, Any
import playwright.async_api
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# 🔥 NEW: Gemini AI Integration
import google.generativeai as genai

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ARTEMIS_URL = "https://artemislivetracker.com/"

# ----------------------------
# 🧠 GEMINI AI SETUP
# ----------------------------
if GEMINI_API_KEY and GEMINI_API_KEY != "None":
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    logger.info("✅ Gemini AI initialized successfully!")
else:
    model = None
    logger.warning("⚠️ No Gemini API key provided - AI chat disabled")

# ----------------------------
# 📊 EMOJI MAPPING & DATA CONFIG
# ----------------------------
DATA_CONFIG = {
    "SPACECRAFT VELOCITY": ("🚀", "Velocity"),
    "DISTANCE FROM EARTH": ("🌍", "Distance from Earth"),
    "DISTANCE FROM MOON": ("🌕", "Distance from Moon"),
    "ALTITUDE ABOVE EARTH": ("🧭", "Altitude"),
    "CABIN TEMP": ("🌡️", "Cabin Temperature"),
    "HEATSHIELD": ("🔥", "Heatshield"),
    "SIGNAL DELAY": ("📡", "Signal Delay"),
    "MISSION PROGRESS": ("📊", "Mission Progress")
}

# ----------------------------
# 🧠 GEMINI AI CHAT HANDLER
# ----------------------------
async def handle_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user questions with Gemini AI about Artemis 2."""
    if not model:
        await update.message.reply_text(
            "❌ *AI Chat Disabled*\n\n"
            "🔑 Please add `GEMINI_API_KEY` to enable AI chat!",
            parse_mode='Markdown'
        )
        return
    
    user_message = update.message.text
    chat_id = update.effective_chat.id
    
    # Send typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Show "AI is thinking..." message
        thinking_msg = await update.message.reply_text(
            "*AI is thinking about Artemis 2...*\n⏳ This may take a few seconds...",
            parse_mode='Markdown'
        )
        
        # Prepare context for Artemis 2
        context_prompt = """
        NASA's Artemis II mission successfully launched on April 1, 2026, at 6:35 p.m. EDT (22:35 UTC) from Kennedy Space Center's Launch Pad 39B in Florida.
        
        You are an expert Artemis 2 mission specialist. Answer questions accurately about:
        - Artemis 2 mission (first crewed Artemis flight)
        - Crew: Reid Wiseman (Commander), Victor Glover (Pilot), Christina Koch, Jeremy Hansen
        - SLS rocket, Orion spacecraft
        - Mission timeline, objectives, lunar flyby
        - NASA Artemis program goals
        
        Keep answers concise (2-4 paragraphs max), use simple language, 
        and add relevant emojis. Always stay on-topic about Artemis 2/NASA.
        """
        
        # Generate response
        response = await model.generate_content_async([context_prompt, user_message])
        ai_answer = response.text
        
        # Edit thinking message with AI response
        await thinking_msg.edit_text(
            f"🚀 Artemis 2 AI Assistant\n\n{ai_answer}\n\nAsk me anything about Artemis 2!"
        )
        
        logger.info(f"✅ AI chat completed for user: {user_message[:50]}...")
        
    except Exception as e:
        error_msg = (
            "🚨 *AI Error!*\n\n"
            "⚠️ Something went wrong with the AI. Try again!\n"
            f"💡 `{str(e)[:100]}...`"
        )
        await thinking_msg.edit_text(error_msg, parse_mode='Markdown')
        logger.error(f"AI chat error: {e}")

# ----------------------------
# 🧠 ADVANCED SCRAPER (unchanged)
# ----------------------------
async def get_artemis_data() -> Dict[str, str]:
    """Robust scraper with comprehensive error handling and retry logic."""
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu"
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()
                
                logger.info(f"🌐 Fetching data (attempt {attempt + 1}/{max_retries})...")
                
                await page.goto(ARTEMIS_URL, timeout=60000)
                await page.wait_for_timeout(8000)
                
                text = await page.inner_text("body")
                logger.info("✅ Page content loaded successfully")
                
                await browser.close()
                
                data = await _parse_data(text)
                return data
                
        except Exception as e:
            logger.error(f"❌ Attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                logger.error("💥 All retry attempts failed")
    
    return {key: "❌ Unavailable" for key in DATA_CONFIG.keys()}

async def _parse_data(text: str) -> Dict[str, str]:
    """Advanced multi-line regex parser with validation."""
    results = {}
    
    for label_raw, (emoji, display_name) in DATA_CONFIG.items():
        pattern = rf"{re.escape(label_raw)}[\s\S]*?([\d,]+\.?\d*)[\s]*([A-Za-z/%°]+)?"
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        
        if match:
            value = match.group(1).replace(",", "")
            unit = match.group(2) if match.group(2) else ""
            results[label_raw] = f"{emoji} `{value} {unit}`".strip()
        else:
            results[label_raw] = f"{emoji} `❌ Not found`"
    
    return results

# ----------------------------
# 🎨 TELEGRAM MESSAGES (unchanged)
# ----------------------------
async def data_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    loading_msg = await update.message.reply_text(
        "🔄 *Fetching Artemis live data...*\n"
        "⏳ Please wait (this takes ~10 seconds)...",
        parse_mode='Markdown'
    )
    
    try:
        data = await get_artemis_data()
        message = _build_artemis_message(data)
        await loading_msg.edit_text(message, parse_mode='Markdown')
        
    except Exception as e:
        error_msg = (
            "🚨 *Error fetching data!*\n\n"
            "⚠️ Please try again later.\n"
            f"💡 Details: `{str(e)[:100]}...`"
        )
        await loading_msg.edit_text(error_msg, parse_mode='Markdown')
        logger.error(f"Error in data_command: {e}")

def _build_artemis_message(data: Dict[str, str]) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S UTC")
    header = f"""*ARTEMIS LIVE TRACKER*

{'='*28}
"""
    
    rows = []
    for i, (label, value) in enumerate(data.items()):
        rows.append(f"{value:<22}")
        if (i + 1) % 3 == 0 or i == len(data) - 1:
            rows.append("\n")
    
    data_section = "".join(rows)
    
    footer = f"""
{'='*28}
*🕐 Last Update:* `{timestamp}`

*Artemis is blasting towards the Moon!*
"""
    
    return header + data_section + footer

# ----------------------------
# 🎯 COMMANDS
# ----------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Welcome message with NEW AI chat instructions."""
    welcome_msg = """*👋 Hola!*

*🚀 Welcome to Artemis Live Tracker + AI Assistant!*

*Commands:*
- /data - Live Artemis mission stats
- /status - Mission overview  
- /help - Show this menu

*🤖 AI Chat:*
Just ask questions like:
"What is Artemis II for?"

Tracking Artemis II journey to the Moon! 🌕

— Designed by *Andrew Bhone (Zay Bhone Aung)*"""
    await update.message.reply_text(welcome_msg, parse_mode='Markdown')

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick status command."""
    await update.message.reply_text(
        """*🚀 ARTEMIS II MISSION INFO*

*👨‍🚀 Crew (4 astronauts):*
- Reid Wiseman - Commander
- Victor Glover - Pilot  
- Christina Koch - Mission Specialist
- Jeremy Hansen - Mission Specialist

*📋 Key Facts:*
- First crewed Artemis mission
- Lunar flyby (no landing)
- Launch: SLS Block 1 rocket
- Spacecraft: Orion

*Target Launch: Late 2025* 🌕""",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help command."""
    await start(update, context)

# ----------------------------
# 🚀 MAIN BOT
# ----------------------------
def main():
    """Initialize and run the bot."""
    if not BOT_TOKEN or BOT_TOKEN == "":
        logger.error("❌ Please set your BOT_TOKEN!")
        return
    
    print("🌟 Starting Artemis Live Tracker + AI Bot...")
    print("🤖 Initializing...")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # 🔥 NEW: AI Chat Handler (catches all text messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_chat))
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("data", data_command))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("help", help_command))
    
    logger.info("✅ Bot is running with AI chat! Press Ctrl+C to stop.")
    print("\n🎉 Bot is LIVE!")
    print("Commands: /start, /data, /status")
    print("AI Chat: Just type questions about Artemis 2!")
    
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        logger.error(f"💥 Fatal error: {e}")