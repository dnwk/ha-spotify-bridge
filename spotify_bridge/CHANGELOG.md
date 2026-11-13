# Changelog

## 0.1.0

First release of the fork. Same code as 0.1.0-dev4.

- One Spotify Connect device ("Home Assistant", librespot 0.8.0) that plays
  through any Music Assistant speaker, as a Sendspin Live Input.
- **Speaker** select entity to choose the speaker; the Spotify volume slider
  sets that speaker's volume.
- Prebuilt images for amd64 and aarch64.
- Known limits: no track info or artwork in Music Assistant, no control from
  Music Assistant back to Spotify, 3-4 s delay on Cast speakers.

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
