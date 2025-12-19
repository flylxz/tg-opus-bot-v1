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
MAX_FILE_SIZE_MB = int(os.environ.get('MAX_FILE_SIZE_MB', '150'))
MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024

# Available bitrates
BITRATES = {
    '16': '16k',
    '24': '24k', 
    '32': '32k'
}

# Default bitrate from environment or use 24
DEFAULT_BITRATE = os.environ.get('DEFAULT_BITRATE', '24')

# Default voice mode - TRUE for speech optimization by default
DEFAULT_VOICE_MODE = True

# Encoding timeout in seconds (default: 30 minutes = 1800 seconds)
ENCODING_TIMEOUT = int(os.environ.get('ENCODING_TIMEOUT', '1800'))


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
    def get_audio_duration(file_path: str) -> float:
        """Get audio duration in seconds using ffprobe"""
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    file_path
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
            return 0.0
        except Exception as e:
            logger.warning(f"Could not get duration: {e}")
            return 0.0
    
    @staticmethod
    def format_duration(seconds: float) -> str:
        """Format duration as MM:SS or HH:MM:SS"""
        if seconds == 0:
            return "N/A"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"
    
    @staticmethod
    def encode_to_opus(
        input_path: str, 
        output_path: str, 
        bitrate: str = "24k",
        application: str = "audio",
        voice_mode: bool = False
    ) -> tuple[bool, str]:
        """
        Encode audio file to Opus format using FFmpeg with libopus
        
        Args:
            input_path: Path to input audio file
            output_path: Path for output Opus file
            bitrate: Audio bitrate (16k, 24k, or 32k)
            application: Opus application mode (audio, voip, or lowdelay)
            voice_mode: If True, optimize for speech (voip mode + mono + packet loss)
            
        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Configure encoding based on voice mode
            if voice_mode:
                app_mode = 'voip'       # Optimize for speech
                packet_loss = '3'       # Packet loss compensation for VoIP
                channels = '1'          # Mono for speech
                logger.info("Voice mode: voip application, mono, packet loss compensation, BWE enabled")
            else:
                app_mode = 'audio'      # Universal mode for music
                packet_loss = '0'       # No packet loss compensation
                channels = None         # Keep original channels (stereo)
                logger.info("Music mode: audio application, original channels, BWE enabled")
            
            # FFmpeg command for Opus encoding
            command = [
                'ffmpeg',
                '-i', input_path,
                '-c:a', 'libopus',           # Use libopus codec (Opus 1.6)
                '-b:a', bitrate,              # Set bitrate
                '-vbr', 'on',                 # Enable Variable Bit Rate
                '-compression_level', '10',   # Maximum compression quality
                '-application', app_mode,     # voip for speech, audio for music
                '-frame_duration', '20',      # Frame duration in ms
                '-packet_loss', packet_loss,  # Packet loss percentage
            ]
            
            # Add BWE (Bandwidth Extension) support - NEW in Opus 1.6!
            # Improves quality at low bitrates by extending bandwidth
            command.extend([
                '-osce_bwe', '1',             # Enable OSCE Bandwidth Extension
                '-complexity', '10'            # Decoder complexity (must be 4+, we use 10 for best quality)
            ])
            
            # Add mono downmix for voice mode
            if channels:
                command.extend(['-ac', channels])  # Downmix to mono
            
            command.extend(['-y', output_path])  # Overwrite output file
            
            logger.info(f"Encoding with command: {' '.join(command)}")
            
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=ENCODING_TIMEOUT  # Configurable timeout (default 30 min)
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully encoded {input_path} with {app_mode} mode")
                return True, ""
            else:
                error_msg = result.stderr
                logger.error(f"FFmpeg error: {error_msg}")
                return False, error_msg
                
        except subprocess.TimeoutExpired:
            error_msg = f"Encoding timeout exceeded ({ENCODING_TIMEOUT // 60} minutes)"
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
            self.user_settings[user_id] = {
                'bitrate': DEFAULT_BITRATE,
                'voice_mode': DEFAULT_VOICE_MODE  # Voice mode ON by default
            }
        
        opus_version = self.encoder.check_opus_version()
        
        welcome_message = (
            "🎵 *Audio to Opus Encoder Bot*\n"
            f"_Powered by Opus {opus_version}_\n\n"
            "Отправь мне:\n"
            "🎧 Аудиофайл\n"
            "🎤 Голосовое сообщение\n"
            "🔗 Ссылку на аудио\n"
            "📎 Пересылку из другого чата\n\n"
            "🎤 *Режим голоса ВКЛЮЧЕН по умолчанию*\n"
            "Оптимизировано для речи (voip + mono)\n\n"
            "*Команды:*\n"
            "/start - Показать это сообщение\n"
            "/help - Справка\n"
            "/bitrate - Выбрать битрейт (16, 24, 32 kbps)\n"
            "/voice - Переключить режим (голос/музыка) 🎤/🎵\n"
            "/settings - Текущие настройки\n\n"
            "*Поддерживаемые форматы:*\n"
            "MP3, WAV, FLAC, AAC, OGG, M4A, WMA и другие!\n\n"
            f"*Максимальный размер:* {MAX_FILE_SIZE_MB}MB"
        )
        await update.message.reply_text(welcome_message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = (
            "*Как использовать:*\n\n"
            "1️⃣ Отправь аудиофайл боту\n"
            "2️⃣ Или отправь голосовое сообщение 🎤\n"
            "3️⃣ Или отправь прямую ссылку на аудио\n"
            "4️⃣ Или перешли аудио из другого чата ➡️\n\n"
            "🎤 *Режим голоса (по умолчанию):*\n"
            "• Application: `voip` (оптимизация для речи)\n"
            "• Каналы: Mono (экономия ~50% места)\n"
            "• Packet Loss: 3% компенсация\n"
            "• Лучше для: речи, подкастов, аудиокниг\n\n"
            "🎵 *Режим музыки:*\n"
            "• Application: `audio` (универсальный)\n"
            "• Каналы: Stereo (полное качество)\n"
            "• Лучше для: музыки, стерео записей\n\n"
            "*Переключение режимов:*\n"
            "Используй /voice для переключения\n\n"
            "*Примеры ссылок:*\n"
            "`https://example.com/audio.mp3`\n"
            "`http://example.com/music/song.wav`\n\n"
            "*Доступные битрейты:*\n"
            "• 16 kbps - для речи (рекомендуется в режиме голоса)\n"
            "• 24 kbps - универсальный (по умолчанию)\n"
            "• 32 kbps - высокое качество для музыки\n\n"
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
        voice_mode = self.user_settings.get(user_id, {}).get('voice_mode', DEFAULT_VOICE_MODE)
        opus_version = self.encoder.check_opus_version()
        
        # Voice mode status
        if voice_mode:
            mode_icon = "🎤"
            mode_name = "Голос (voip)"
            mode_desc = "Моно, оптимизация для речи"
            packet_loss = "3% (компенсация)"
        else:
            mode_icon = "🎵"
            mode_name = "Музыка (audio)"
            mode_desc = "Стерео, полное качество"
            packet_loss = "0%"
        
        settings_text = (
            "*Текущие настройки:*\n\n"
            f"🔊 Битрейт: *{bitrate} kbps*\n"
            f"{mode_icon} Режим: *{mode_name}*\n"
            f"   └ {mode_desc}\n"
            f"📦 Кодек: Opus {opus_version} (libopus)\n"
            f"🎚️ VBR: Включен\n"
            f"⚙️ Сжатие: 10 (максимальное)\n"
            f"🌊 BWE: Включен (Opus 1.6)\n"
            f"🧮 Complexity: 10\n"
            f"📡 Packet Loss: {packet_loss}\n"
            f"⏱️ Фрейм: 20ms\n"
            f"📏 Макс. размер: {MAX_FILE_SIZE_MB} MB\n"
            f"⏲️ Timeout: {ENCODING_TIMEOUT // 60} мин\n\n"
            f"Команды:\n"
            f"• /bitrate - изменить битрейт\n"
            f"• /voice - переключить режим (голос/музыка)"
        )
        await update.message.reply_text(settings_text, parse_mode='Markdown')
    
    async def voice_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /voice command - toggle voice mode (voip optimization)"""
        user_id = update.effective_user.id
        
        # Initialize if needed
        if user_id not in self.user_settings:
            self.user_settings[user_id] = {
                'bitrate': DEFAULT_BITRATE,
                'voice_mode': DEFAULT_VOICE_MODE
            }
        
        # Toggle voice mode
        current_voice_mode = self.user_settings[user_id].get('voice_mode', DEFAULT_VOICE_MODE)
        new_voice_mode = not current_voice_mode
        self.user_settings[user_id]['voice_mode'] = new_voice_mode
        
        if new_voice_mode:
            # Voice mode ON
            message = (
                "🎤 *Режим голоса ВКЛЮЧЕН*\n\n"
                "*Оптимизация для речи:*\n"
                "✅ Application: `voip` (для голоса)\n"
                "✅ Каналы: Mono (экономия ~50%)\n"
                "✅ Packet Loss: 3% (компенсация)\n"
                "✅ Частоты: речевой диапазон (80Hz-8kHz)\n\n"
                "*Идеально для:*\n"
                "🎤 Голосовых сообщений\n"
                "🎙️ Подкастов\n"
                "📚 Аудиокниг\n"
                "🗣️ Записей речи\n"
                "📞 Звонков и интервью\n\n"
                "*Рекомендуемый битрейт:* 16-24 kbps\n"
                "Используй /bitrate для изменения"
            )
        else:
            # Voice mode OFF (Music mode ON)
            message = (
                "🎵 *Режим музыки ВКЛЮЧЕН*\n\n"
                "*Универсальное качество:*\n"
                "✅ Application: `audio` (универсальный)\n"
                "✅ Каналы: Stereo (полное качество)\n"
                "✅ Частоты: полный диапазон (20Hz-20kHz)\n\n"
                "*Идеально для:*\n"
                "🎵 Музыки\n"
                "🎧 Стерео записей\n"
                "🎬 Звуковых дорожек\n"
                "🎸 Концертов\n\n"
                "*Рекомендуемый битрейт:* 24-32 kbps\n"
                "Используй /bitrate для изменения"
            )
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
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
                
                # Get voice mode
                voice_mode = self.user_settings.get(user_id, {}).get('voice_mode', DEFAULT_VOICE_MODE)
                mode_icon = "🎤" if voice_mode else "🎵"
                mode_text = "voip, mono" if voice_mode else "audio, stereo"
                
                # Get audio duration
                duration_seconds = self.encoder.get_audio_duration(input_path)
                duration_str = self.encoder.format_duration(duration_seconds)
                
                # Encode to Opus
                await status_msg.edit_text(
                    f"🔄 Кодирую в Opus {bitrate} kbps...\n"
                    f"{mode_icon} Режим: {mode_text}\n"
                    f"⏱️ Длительность: {duration_str}",
                    parse_mode='Markdown'
                )
                
                success, error = self.encoder.encode_to_opus(
                    input_path, output_path, bitrate_value, voice_mode=voice_mode
                )
                
                if success and os.path.exists(output_path):
                    # Get file sizes
                    input_size = os.path.getsize(input_path)
                    output_size = os.path.getsize(output_path)
                    compression_ratio = (1 - output_size / input_size) * 100
                    
                    # Send encoded file
                    await status_msg.edit_text("📤 Отправляю файл...")
                    
                    caption = (
                        f"✅ Opus {bitrate} kbps\n"
                        f"{mode_icon} {mode_text}\n"
                        f"⏱️ Длительность: {duration_str}\n"
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
                    # Show detailed error
                    error_preview = error[:200] + "..." if len(error) > 200 else error
                    await status_msg.edit_text(
                        f"❌ Ошибка кодирования:\n\n"
                        f"`{error_preview}`\n\n"
                        f"Попробуй другой файл или измени настройки:\n"
                        f"• /bitrate - изменить битрейт\n"
                        f"• /voice - изменить режим",
                        parse_mode='Markdown'
                    )
                    logger.error(f"Full encoding error for user {user_id}: {error}")
                    
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
                
                # Get voice mode
                voice_mode = self.user_settings.get(user_id, {}).get('voice_mode', DEFAULT_VOICE_MODE)
                mode_icon = "🎤" if voice_mode else "🎵"
                mode_text = "voip, mono" if voice_mode else "audio, stereo"
                
                # Get audio duration
                duration_seconds = self.encoder.get_audio_duration(input_path)
                duration_str = self.encoder.format_duration(duration_seconds)
                
                # Encode to Opus
                await status_msg.edit_text(
                    f"🔄 Кодирую в Opus {bitrate} kbps...\n"
                    f"{mode_icon} Режим: {mode_text}\n"
                    f"⏱️ Длительность: {duration_str}",
                    parse_mode='Markdown'
                )
                
                success, error = self.encoder.encode_to_opus(
                    input_path, output_path, bitrate_value, voice_mode=voice_mode
                )
                
                if success and os.path.exists(output_path):
                    # Get file sizes
                    input_size = os.path.getsize(input_path)
                    output_size = os.path.getsize(output_path)
                    compression_ratio = (1 - output_size / input_size) * 100
                    
                    # Send encoded file
                    await status_msg.edit_text("📤 Отправляю файл...")
                    
                    caption = (
                        f"✅ Opus {bitrate} kbps\n"
                        f"{mode_icon} {mode_text}\n"
                        f"⏱️ Длительность: {duration_str}\n"
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
                    # Show detailed error
                    error_preview = error[:200] + "..." if len(error) > 200 else error
                    await status_msg.edit_text(
                        f"❌ Ошибка кодирования:\n\n"
                        f"`{error_preview}`\n\n"
                        f"Попробуй другой файл или измени настройки:\n"
                        f"• /bitrate - изменить битрейт\n"
                        f"• /voice - изменить режим",
                        parse_mode='Markdown'
                    )
                    logger.error(f"Full encoding error for user {user_id}: {error}")
                    
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
        application.add_handler(CommandHandler("voice", self.voice_command))
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
    logger.info(f"Default voice mode: {'ON (voip, mono)' if DEFAULT_VOICE_MODE else 'OFF (audio, stereo)'}")
    logger.info(f"Encoding timeout: {ENCODING_TIMEOUT} seconds ({ENCODING_TIMEOUT // 60} minutes)")
    
    # Start health check server in background
    health_thread = threading.Thread(target=start_health_server, daemon=True)
    health_thread.start()
    
    bot = TelegramAudioBot(TELEGRAM_BOT_TOKEN)
    bot.run()


if __name__ == '__main__':
    main()