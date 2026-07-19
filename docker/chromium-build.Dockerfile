FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        file \
        git \
        lsb-release \
        python3 \
        python3-pkg-resources \
        ninja-build \
        sudo \
        xz-utils \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 https://chromium.googlesource.com/chromium/tools/depot_tools.git /opt/depot_tools

ENV PATH="/opt/depot_tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ENV DEPOT_TOOLS_UPDATE=0

WORKDIR /work/chromium/src

CMD ["bash", "-lc", "python3 --version && git --version && gclient --version"]
