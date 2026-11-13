ARG BUILD_FROM=ghcr.io/hassio-addons/base:21.0.11
# hadolint ignore=DL3006
FROM ${BUILD_FROM}

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Setup base
ARG LIBRESPOT_VERSION="0.8.0"
# hadolint ignore=DL3003
RUN \
    apk add --no-cache \
        libssl3=3.5.9-r0 \
        libcrypto3=3.5.9-r0 \
    \
    && apk add --no-cache --virtual .build-dependencies \
        build-base=0.5-r4 \
        cargo=1.96.1-r0 \
        git=2.54.1-r0 \
        protobuf-dev=31.1-r1 \
        cmake=4.2.3-r0 \
        clang20-libclang=20.1.8-r3 \
        openssl-dev=3.5.9-r0 \
    \
    && cargo install --force --locked bindgen-cli \
    && export PATH="$HOME/.cargo/bin:$PATH" \
    && cargo install \
        --locked \
        --no-default-features \
        --features "native-tls with-libmdns" \
        --root /usr \
        --bin librespot \
        --version "${LIBRESPOT_VERSION}" \
        --verbose \
        -- librespot \
    \
    && cargo uninstall bindgen-cli \
    && apk del --no-cache --purge .build-dependencies \
    && rm -fr \
        /tmp/* \
        ~/.cargo \
        /usr/.crates.toml \
        /usr/.crates2.json

# Spotify Bridge: Python service that reads librespot's PCM pipe and events
# (librespot is built without PulseAudio; it writes to a FIFO instead).
COPY bridge /tmp/bridge
RUN \
    apk add --no-cache \
        python3=3.14.10-r1 \
    \
    && python3 -m venv /opt/spotify-bridge \
    && /opt/spotify-bridge/bin/pip install --no-cache-dir /tmp/bridge \
    && rm -fr /tmp/bridge

# Copy root filesystem
COPY rootfs /
# Copies made from Windows (Samba / local add-on folder) lose the executable bit.
RUN chmod a+x \
        /etc/cont-init.d/spotify-bridge.sh \
        /etc/services.d/librespot/run /etc/services.d/librespot/finish \
        /etc/services.d/bridge/run /etc/services.d/bridge/finish

# Build arguments
ARG BUILD_ARCH
ARG BUILD_DATE
ARG BUILD_DESCRIPTION
ARG BUILD_NAME
ARG BUILD_REF
ARG BUILD_REPOSITORY
ARG BUILD_VERSION

# Labels
LABEL \
    io.hass.name="${BUILD_NAME}" \
    io.hass.description="${BUILD_DESCRIPTION}" \
    io.hass.arch="${BUILD_ARCH}" \
    io.hass.type="addon" \
    io.hass.version=${BUILD_VERSION} \
    maintainer="dnwk (fork; upstream app by Franck Nijhof)" \
    org.opencontainers.image.title="${BUILD_NAME}" \
    org.opencontainers.image.description="${BUILD_DESCRIPTION}" \
    org.opencontainers.image.vendor="Spotify Bridge (fork of Home Assistant Community Apps' Spotify Connect)" \
    org.opencontainers.image.authors="dnwk; upstream Spotify Connect app by Franck Nijhof" \
    org.opencontainers.image.licenses="MIT" \
    org.opencontainers.image.url="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.source="https://github.com/${BUILD_REPOSITORY}" \
    org.opencontainers.image.documentation="https://github.com/${BUILD_REPOSITORY}/blob/bridge/spotify_bridge/DOCS.md" \
    org.opencontainers.image.created=${BUILD_DATE} \
    org.opencontainers.image.revision=${BUILD_REF} \
    org.opencontainers.image.version=${BUILD_VERSION}
