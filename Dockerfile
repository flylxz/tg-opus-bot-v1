# ================= BUILD STAGE =================
FROM python:3.11-slim AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libogg-dev \
    ffmpeg \
    wget \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# ---------- libopus 1.6 (official tarball) ----------
RUN wget https://downloads.xiph.org/releases/opus/opus-1.6.tar.gz && \
    tar xzf opus-1.6.tar.gz && \
    cd opus-1.6 && \
    ./configure --disable-shared --enable-static && \
    make -j$(nproc) && \
    make install

# IMPORTANT: make pkg-config see libopus
ENV PKG_CONFIG_PATH=/usr/local/lib/pkgconfig

# ---------- opus-tools (git) ----------
RUN git clone https://gitlab.xiph.org/xiph/opus-tools.git && \
    cd opus-tools && \
    ./autogen.sh && \
    ./configure && \
    make -j$(nproc) && \
    make install

# ================= RUNTIME STAGE =================
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /usr/local /usr/local

WORKDIR /app
RUN pip install --no-cache-dir \
    python-telegram-bot==20.7 \
    yt-dlp \
    requests

COPY bot.py .

CMD ["python", "bot.py"]
