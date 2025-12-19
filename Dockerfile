FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

# Install dependencies and Opus 1.6
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    tar \
    pkg-config \
    autoconf \
    automake \
    libtool \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Build Opus 1.6 with OSCE/BWE support
RUN cd /tmp && \
    wget https://downloads.xiph.org/releases/opus/opus-1.6.tar.gz && \
    tar -xzf opus-1.6.tar.gz && \
    cd opus-1.6 && \
    ./configure --prefix=/usr/local --enable-osce && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    rm -rf /tmp/opus-*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot
COPY telegram_audio_bot.py .

CMD ["python", "-u", "telegram_audio_bot.py"]