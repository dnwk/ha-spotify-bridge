# Changelog

## 0.1.0-dev4

- Images are now prebuilt by GitHub Actions (amd64 and aarch64) and pulled by
  Home Assistant; installing or updating no longer compiles librespot locally.
- Image labels name this fork (upstream credited).

## 0.1.0-dev3

- The Spotify volume slider sets the volume of the speaker that plays it.
- New **Speaker** select entity (MQTT) to choose where Spotify plays.
- Docs: delay depends on the speaker (Cast about 3-4 s, Sendspin much less).

## 0.0.x (dev)

- Spotify Connect (librespot 0.8.0) feeding Music Assistant as a Sendspin
  Live Input; pairing via an HA notification or a fixed 8-digit code.
