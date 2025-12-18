FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    tar \
    pkg-config \
    autoconf \
    automake \
    libtool \
    yasm \
    nasm \
    git \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install Opus 1.6 from source
RUN cd /tmp && \
    wget https://downloads.xiph.org/releases/opus/opus-1.6.tar.gz && \
    tar -xzf opus-1.6.tar.gz && \
    cd opus-1.6 && \
    ./configure --prefix=/usr/local --enable-float-approx && \
    make -j$(nproc) && \
    make install && \
    ldconfig && \
    cd / && \
    rm -rf /tmp/opus-1.6*

# Verify Opus installation
RUN pkg-config --modversion opus && \
    echo "Opus installed successfully!"

# Verify FFmpeg has Opus support
RUN ffmpeg -codecs 2>/dev/null | grep opus || echo "Warning: Opus codec check"

# Copy requirements first for better caching
COPY requirements.txt /tmp/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create app directory and copy files
WORKDIR /app
COPY . .

# Create directory for temporary files
RUN mkdir -p /tmp/audio_temp && chmod 777 /tmp/audio_temp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Run the bot
CMD ["python", "-u", "telegram_audio_bot.py"]