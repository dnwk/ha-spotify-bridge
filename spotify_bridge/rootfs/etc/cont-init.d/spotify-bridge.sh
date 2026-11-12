#!/command/with-contenv bashio
# shellcheck shell=bash
# ==============================================================================
# Spotify Bridge
# Creates the runtime directory, the PCM FIFO (librespot -> bridge) and the
# directory for the event socket (librespot --onevent -> bridge).
# ==============================================================================
readonly RUNTIME_DIR=/run/spotify-bridge
readonly FIFO="${RUNTIME_DIR}/audio.fifo"

install -d -m 0755 "${RUNTIME_DIR}"

if [[ -e "${FIFO}" && ! -p "${FIFO}" ]]; then
  rm -f "${FIFO}"
fi

if [[ ! -p "${FIFO}" ]]; then
  mkfifo -m 0600 "${FIFO}"
fi

bashio::log.info "Audio FIFO ready at ${FIFO}"
