RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    autoconf \
    automake \
    libtool \
    pkg-config \
    libogg-dev \
    m4 \
    gettext \
    ffmpeg \
    wget \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
