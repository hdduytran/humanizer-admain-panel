
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler
import os


class TelegramHandler():
    def __init__(self, bot_token):
        self.bot = Bot(bot_token)
        self.text_limit = 2000
        
    def notify(self, user_id, message):
        asyncio.get_event_loop().run_until_complete(self.bot.send_message(chat_id=user_id, text=message))
        
    async def __notify(self, user_id, message):
        await self.bot.send_message(chat_id=user_id, text=message)
        
    async def _notify_all(self, message, user_ids):
        for user in user_ids:
            await self.__notify(user, message)
            
    def notify_all(self, message, user_ids):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        asyncio.get_event_loop().run_until_complete(self._notify_all(message, user_ids))
            