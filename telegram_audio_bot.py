#!/usr/bin/env python3
"""
Telegram Bot for Audio Encoding to Opus Codec
Uses Opus 1.6 with selectable bitrates: 16, 24, 32 kbps
Handles both direct file uploads and audio file links
"""

import os
import logging
import subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)
import requests
from pathlib import Path
import tempfile
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', '50'))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# Available bitrates
BITRATES = {
    '16': '16k',
    '24': '24k', 
    '32': '32k'
}

# Default bitrate from environment or use 24
DEFAULT_BITRATE = os.environ.get('DEFAULT_BITRATE', '24')


# Simple HTTP server for health checks
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/health' or self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b'OK - Bot is running')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP logs
        pass


def start_health_server(port=8000):
    """Start HTTP server for health checks in background thread"""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server started on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Could not start health check server: {e}")


class AudioEncoder:
    """Handles audio encoding to Opus format using Opus 1.6"""
    
    @staticmethod
    def check_opus_version() -> str:
        """Check installed Opus version"""
        try:
            result = subprocess.run(
                ['pkg-config', '--modversion', 'opus'],
                capture_output=True,
                text=True
            )
            return result.stdout.strip() if result.returncode == 0 else "Unknown"
        except Exception:
            return "Unknown"
    
    @staticmethod
    def encode_to_opus(
        input_path: str, 
        output_path: str, 
        bitrate: str = "24k",
        application: str = "audio"
    ) -> tuple[bool, str]:
        """
        Encode audio file to Opus format using FFmpeg with libopus
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output Opus file
            bitrate: Audio bitrate (16k, 24k, or 32k)
            application: Opus application mode (audio, voip, or lowdelay)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # FFmpeg command for Opus encoding
            command = [
                'ffmpeg',
                '-i', input_path,
                '-c:a', 'libopus',           # Use libopus codec (Opus 1.6)
                '-b:a', bitrate,              # Set bitrate
                '-vbr', 'on',                 # Enable Variable Bit Rate
                '-compression_level', '10',   # Maximum compression quality
                '-application', application,  # Application mode
                '-frame_duration', '20',      # Frame duration in ms
                '-packet_loss', '0',          # Packet loss percentage
                '-y',                         # Overwrite output file
                output_path
            ]
            
            logger.info(f"Encoding with command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully encoded {input_path} to {output_path}")
                return True, ""
            else:
                error_msg = result.stderr
                logger.error(f"FFmpeg error: {error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = "Encoding timeout exceeded (5 minutes)"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Encoding error: {error_msg}")
            return False, error_msg


class TelegramAudioBot:
    """Main bot class with bitrate selection"""
    
    def __init__(self, token: str):
        self.token = token
        self.encoder = AudioEncoder()
        # Store user preferences (bitrate)
        self.user_settings = {}
        
    def get_bitrate_keyboard(self, current_bitrate: str = None) -> InlineKeyboardMarkup:
        """Create inline keyboard for bitrate selection"""
        keyboard = []
        for key, value in BITRATES.items():
            label = f"{'✓ ' if current_bitrate == key else ''}{key} kbps"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"bitrate_{key}")])
        
        return InlineKeyboardMarkup(keyboard)
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {'bitrate': DEFAULT_BITRATE}
        
        opus_version = self.encoder.check_opus_version()
        
        welcome_message = (
            "🎵 *Audio to Opus Encoder Bot*\n"
            f"_Powered by Opus {opus_version}_\n\n"
            "Отправь мне аудиофайл или ссылку на аудио, "
            "и я конвертирую его в формат Opus!\n\n"
            "*Команды:*\n"
            "/start - Показать это сообщение\n"
            "/help - Справка\n"
            "/bitrate - Выбрать битрейт (16, 24, 32 kbps)\n"
            "/settings - Текущие настройки\n\n"
            "*Поддерживаемые форматы:*\n"
            "MP3, WAV, FLAC, AAC, OGG, M4A, WMA и другие!\n\n"
            "*Максимальный размер:* 50MB"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "*Как использовать:*\n\n"
            "1️⃣ Отправь аудиофайл боту\n"
            "2️⃣ Или отправь прямую ссылку на аудио\n"
            "3️⃣ Выбери битрейт командой /bitrate\n\n"
            "*Примеры ссылок:*\n"
            "`https://example.com/audio.mp3`\n"
            "`http://example.com/music/song.wav`\n\n"
            "*Доступные битрейты:*\n"
            "• 16 kbps - для речи\n"
            "• 24 kbps - универсальный (по умолчанию)\n"
            "• 32 kbps - высокое качество\n\n"
            "*Кодек:*\n"
            "Opus 1.6 (оптимизирован для речи и музыки)"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def bitrate_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bitrate command"""
        user_id = update.effective_user.id
        current_bitrate = self.user_settings.get(user_id, {}).get('bitrate', DEFAULT_BITRATE)
        
        keyboard = self.get_bitrate_keyboard(current_bitrate)
        
        await update.message.reply_text(
            f"*Выбери битрейт:*\n\n"
            f"Текущий: *{current_bitrate} kbps*\n\n"
            f"• 16 kbps - для речи, минимальный размер\n"
            f"• 24 kbps - баланс качества и размера\n"
            f"• 32 kbps - высокое качество для музыки",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def bitrate_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle bitrate selection callback"""
        query = update.callback_query
        await query.answer()
        
        user_id = update.effective_user.id
        bitrate = query.data.split('_')[1]
        
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {}
        
        self.user_settings[user_id]['bitrate'] = bitrate
        
        keyboard = self.get_bitrate_keyboard(bitrate)
        
        await query.edit_message_text(
            f"✅ *Битрейт установлен: {bitrate} kbps*\n\n"
            f"Теперь отправь аудиофайл для конвертации!",
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    async def settings_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command"""
        user_id = update.effective_user.id
        bitrate = self.user_settings.get(user_id, {}).get('bitrate', DEFAULT_BITRATE)
        opus_version = self.encoder.check_opus_version()
        
        settings_text = (
            "*Текущие настройки:*\n\n"
            f"🔊 Битрейт: *{bitrate} kbps*\n"
            f"📦 Кодек: Opus {opus_version} (libopus)\n"
            f"🎚️ VBR: Включен\n"
            f"⚙️ Уровень сжатия: 10 (максимальный)\n"
            f"📱 Режим: Audio (универсальный)\n"
            f"⏱️ Длина фрейма: 20ms\n"
            f"📏 Макс. размер файла: 50 MB\n\n"
            f"Используй /bitrate для изменения битрейта"
        )
        await update.message.reply_text(settings_text, parse_mode='Markdown')
    
    async def handle_audio_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio file uploads"""
        message = update.message
        user_id = update.effective_user.id
        
        # Get user bitrate preference
        bitrate = self.user_settings.get(user_id, {}).get('bitrate', DEFAULT_BITRATE)
        bitrate_value = BITRATES[bitrate]
        
        # Get audio file
        if message.audio:
            audio = message.audio
        elif message.voice:
            audio = message.voice
        elif message.document and message.document.mime_type and 'audio' in message.document.mime_type:
            audio = message.document
        else:
            await message.reply_text("❌ Пожалуйста, отправь аудиофайл или ссылку.")
            return
        
        # Check file size
        if audio.file_size > MAX_FILE_SIZE:
            await message.reply_text(
                f"❌ Файл слишком большой! Максимум {MAX_FILE_SIZE // (1024*1024)}MB"
            )
            return
        
        # Send processing message
        status_msg = await message.reply_text(
            f"⏳ Скачиваю и кодирую аудио...\n"
            f"Битрейт: *{bitrate} kbps*",
            parse_mode='Markdown'
        )
        
        try:
            # Create temporary directory
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download file
                file = await audio.get_file()
                input_filename = audio.file_name if hasattr(audio, 'file_name') and audio.file_name else f"audio_{audio.file_unique_id}"
                input_path = os.path.join(temp_dir, input_filename)
                
                await file.download_to_drive(input_path)
                
                # Prepare output path
                output_filename = Path(input_filename).stem + ".opus"
                output_path = os.path.join(temp_dir, output_filename)
                
                # Encode to Opus
                await status_msg.edit_text(
                    f"🔄 Кодирую в Opus {bitrate} kbps...",
                    parse_mode='Markdown'
                )
                
                success, error = self.encoder.encode_to_opus(input_path, output_path, bitrate_value)
                
                if success and os.path.exists(output_path):
                    # Get file sizes
                    input_size = os.path.getsize(input_path)
                    output_size = os.path.getsize(output_path)
                    compression_ratio = (1 - output_size / input_size) * 100
                    
                    # Send encoded file
                    await status_msg.edit_text("📤 Отправляю файл...")
                    
                    caption = (
                        f"✅ Закодировано в Opus {bitrate} kbps\n"
                        f"📉 Сжатие: {compression_ratio:.1f}%\n"
                        f"📦 Размер: {output_size / 1024:.1f} KB"
                    )
                    
                    with open(output_path, 'rb') as opus_file:
                        await message.reply_audio(
                            audio=opus_file,
                            filename=output_filename,
                            caption=caption
                        )
                    
                    await status_msg.delete()
                else:
                    await status_msg.edit_text(
                        f"❌ Ошибка кодирования.\n"
                        f"Попробуй другой файл или измени битрейт через /bitrate"
                    )
                    
        except Exception as e:
            logger.error(f"Error processing audio file: {str(e)}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    
    async def handle_audio_link(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle audio file links"""
        message = update.message
        user_id = update.effective_user.id
        url = message.text.strip()
        
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            return  # Not a URL, ignore
        
        # Get user bitrate preference
        bitrate = self.user_settings.get(user_id, {}).get('bitrate', DEFAULT_BITRATE)
        bitrate_value = BITRATES[bitrate]
        
        # Send processing message
        status_msg = await message.reply_text(
            f"⏳ Скачиваю аудио по ссылке...\n"
            f"Битрейт: *{bitrate} kbps*",
            parse_mode='Markdown'
        )
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download file from URL
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                # Check content type
                content_type = response.headers.get('content-type', '')
                if 'audio' not in content_type and not any(ext in url.lower() for ext in ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.opus']):
                    await status_msg.edit_text("❌ Ссылка не ведёт на аудиофайл.")
                    return
                
                # Get filename from URL or use default
                filename = url.split('/')[-1].split('?')[0] or 'audio.mp3'
                input_path = os.path.join(temp_dir, filename)
                
                # Save downloaded file
                with open(input_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                file_size = os.path.getsize(input_path)
                if file_size > MAX_FILE_SIZE:
                    await status_msg.edit_text(
                        f"❌ Файл слишком большой! Максимум {MAX_FILE_SIZE // (1024*1024)}MB"
                    )
                    return
                
                # Prepare output path
                output_filename = Path(filename).stem + ".opus"
                output_path = os.path.join(temp_dir, output_filename)
                
                # Encode to Opus
                await status_msg.edit_text(
                    f"🔄 Кодирую в Opus {bitrate} kbps...",
                    parse_mode='Markdown'
                )
                
                success, error = self.encoder.encode_to_opus(input_path, output_path, bitrate_value)
                
                if success and os.path.exists(output_path):
                    # Get file sizes
                    input_size = os.path.getsize(input_path)
                    output_size = os.path.getsize(output_path)
                    compression_ratio = (1 - output_size / input_size) * 100
                    
                    # Send encoded file
                    await status_msg.edit_text("📤 Отправляю файл...")
                    
                    caption = (
                        f"✅ Закодировано в Opus {bitrate} kbps\n"
                        f"📉 Сжатие: {compression_ratio:.1f}%\n"
                        f"📦 Размер: {output_size / 1024:.1f} KB"
                    )
                    
                    with open(output_path, 'rb') as opus_file:
                        await message.reply_audio(
                            audio=opus_file,
                            filename=output_filename,
                            caption=caption
                        )
                    
                    await status_msg.delete()
                else:
                    await status_msg.edit_text(
                        f"❌ Ошибка кодирования.\n"
                        f"Попробуй другой файл или измени битрейт через /bitrate"
                    )
                    
        except requests.RequestException as e:
            logger.error(f"Error downloading from URL: {str(e)}")
            await status_msg.edit_text("❌ Не удалось скачать аудио. Проверь ссылку.")
        except Exception as e:
            logger.error(f"Error processing audio link: {str(e)}")
            await status_msg.edit_text(f"❌ Ошибка: {str(e)}")
    
    def run(self):
        """Start the bot"""
        # Create application
        application = Application.builder().token(self.token).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("bitrate", self.bitrate_command))
        application.add_handler(CommandHandler("settings", self.settings_command))
        
        # Handle bitrate selection
        application.add_handler(CallbackQueryHandler(self.bitrate_callback, pattern="^bitrate_"))
        
        # Handle audio files
        application.add_handler(MessageHandler(
            filters.AUDIO | filters.VOICE | filters.Document.AUDIO,
            self.handle_audio_file
        ))
        
        # Handle text messages (for links)
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            self.handle_audio_link
        ))
        
        # Start the bot
        logger.info("Bot started with Opus 1.6 support!")
        application.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """Main entry point"""
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Пожалуйста, установи переменную окружения TELEGRAM_BOT_TOKEN!")
        print("Получи токен от @BotFather в Telegram")
        print("\nПример:")
        print("export TELEGRAM_BOT_TOKEN='your_token_here'")
        print("или создай файл .env с TELEGRAM_BOT_TOKEN=your_token_here")
        return
    
    logger.info(f"Starting bot with Opus 1.6")
    logger.info(f"Max file size: {MAX_FILE_SIZE_MB}MB")
    logger.info(f"Default bitrate: {DEFAULT_BITRATE}kbps")
    
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    bot = TelegramAudioBot(TELEGRAM_BOT_TOKEN)
    bot.run()


if __name__ == '__main__':
    main()