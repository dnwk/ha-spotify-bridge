"""Spotify Bridge: librespot (pipe backend) into Music Assistant."""

RUNTIME_DIR = "/run/spotify-bridge"
FIFO_PATH = f"{RUNTIME_DIR}/audio.fifo"
EVENT_SOCKET_PATH = f"{RUNTIME_DIR}/events.sock"

# librespot --format S16 on the pipe backend: interleaved s16le, 44.1 kHz, stereo.
SAMPLE_RATE = 44_100
CHANNELS = 2
BYTES_PER_SAMPLE = 2
FRAME_BYTES = CHANNELS * BYTES_PER_SAMPLE
