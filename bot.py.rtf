{\rtf1\ansi\ansicpg1252\cocoartf2822
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 import os, subprocess, tempfile, requests, logging\
import yt_dlp\
from telegram import Update\
from telegram.ext import (\
    ApplicationBuilder, MessageHandler, CommandHandler,\
    ContextTypes, filters\
)\
\
TOKEN = os.getenv("BOT_TOKEN")\
\
MAX_SECONDS = 3 * 3600\
BITRATE = 16\
MODE = "speech"\
\
WHITELIST = \{\
    1545452,  # <-- \uc0\u1058 \u1042 \u1054 \u1049  TELEGRAM ID\
\}\
\
logging.basicConfig(\
    level=logging.INFO,\
    format="%(asctime)s | %(message)s"\
)\
\
subprocess.run(["yt-dlp", "-U"], stdout=subprocess.DEVNULL)\
\
async def set_bitrate(update: Update, context: ContextTypes.DEFAULT_TYPE):\
    global BITRATE\
    if context.args and context.args[0] in ["16", "24", "32"]:\
        BITRATE = int(context.args[0])\
        await update.message.reply_text(f"\uc0\u1041 \u1080 \u1090 \u1088 \u1077 \u1081 \u1090 : \{BITRATE\} kbps")\
\
async def set_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):\
    global MODE\
    if context.args and context.args[0] in ["speech", "music"]:\
        MODE = context.args[0]\
        await update.message.reply_text(f"\uc0\u1056 \u1077 \u1078 \u1080 \u1084 : \{MODE\}")\
\
async def process(update: Update, context: ContextTypes.DEFAULT_TYPE):\
    uid = update.effective_user.id\
    if uid not in WHITELIST:\
        await update.message.reply_text("\uc0\u9940  \u1044 \u1086 \u1089 \u1090 \u1091 \u1087  \u1079 \u1072 \u1087 \u1088 \u1077 \u1097 \u1105 \u1085 ")\
        return\
\
    url = update.message.text.strip()\
    await update.message.reply_text("\uc0\u55357 \u56580  \u1055 \u1086 \u1083 \u1091 \u1095 \u1072 \u1102  \u1072 \u1091 \u1076 \u1080 \u1086 ...")\
\
    with tempfile.NamedTemporaryFile(delete=False) as f:\
        input_path = f.name\
\
    title = "audio"\
\
    try:\
        if "youtu" in url:\
            ydl_opts = \{\
                "format": "bestaudio/best",\
                "outtmpl": input_path,\
                "quiet": True,\
                "noplaylist": True,\
            \}\
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:\
                info = ydl.extract_info(url, download=True)\
                title = info.get("title", "youtube_audio")\
        else:\
            r = requests.get(url, stream=True, timeout=15)\
            with open(input_path, "wb") as f:\
                for chunk in r.iter_content(8192):\
                    f.write(chunk)\
\
        duration = float(subprocess.check_output([\
            "ffprobe", "-v", "error",\
            "-show_entries", "format=duration",\
            "-of", "default=nokey=1:noprint_wrappers=1",\
            input_path\
        ]))\
\
        if duration > MAX_SECONDS:\
            await update.message.reply_text("\uc0\u10060  \u1040 \u1091 \u1076 \u1080 \u1086  > 3 \u1095 \u1072 \u1089 \u1086 \u1074 ")\
            return\
\
        output = f"\{title\}.opus".replace("/", "_")\
\
        ffmpeg = subprocess.Popen(\
            ["ffmpeg", "-i", input_path, "-ac", "1", "-ar", "48000", "-f", "wav", "-"],\
            stdout=subprocess.PIPE\
        )\
\
        opusenc = subprocess.Popen(\
            ["opusenc", f"--\{MODE\}", "--bitrate", str(BITRATE), "-", output],\
            stdin=ffmpeg.stdout\
        )\
\
        opusenc.wait()\
        ffmpeg.wait()\
\
        await update.message.reply_document(open(output, "rb"))\
\
    finally:\
        for f in [input_path, output if 'output' in locals() else None]:\
            if f and os.path.exists(f):\
                os.remove(f)\
\
app = ApplicationBuilder().token(TOKEN).build()\
app.add_handler(CommandHandler("bitrate", set_bitrate))\
app.add_handler(CommandHandler("mode", set_mode))\
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, process))\
app.run_polling()\
}