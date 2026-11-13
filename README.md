# Spotify Bridge for Home Assistant

A fork of the Home Assistant Community app [Spotify Connect](https://github.com/hassio-addons/app-spotify-connect) by Franck Nijhof.

The upstream app plays Spotify through the Home Assistant host's own sound output. This fork sends the audio into **[Music Assistant](https://music-assistant.io)** as a Sendspin **Live Input** instead. You keep one Spotify Connect device ("Home Assistant"), and you choose in Music Assistant which speaker actually plays it: Cast displays and TVs, Home Assistant Voice PE, sync groups, and so on.

> **Status: 0.1.0, first release.** Tested on one amd64 HAOS install with Music Assistant 2.10.9; the aarch64 image is built but has not been tried on hardware.

## Install

[![Add repository to my Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fdnwk%2Fha-spotify-bridge)

Or: Settings → Apps → App store → ⋮ → Repositories → add `https://github.com/dnwk/ha-spotify-bridge`, then install **Spotify Bridge**. Setup, pairing and options are in [spotify_bridge/DOCS.md](spotify_bridge/DOCS.md).

## How it works

```
Spotify app ──Connect──▶ librespot (pipe backend) ──PCM──▶ bridge (Python, aiosendspin)
                                                              │ Sendspin source role + line-sense
                                                              ▼
                                            Music Assistant "Live Input" ──▶ any MA speaker / group
```

- **librespot 0.8.0** (as upstream) writes decoded audio to a FIFO and reports play, pause and volume events.
- The **bridge** is a paired Sendspin *source* client. When Spotify plays, it reports "signal present" and starts the source on the speaker chosen with the **Speaker** select entity (or Music Assistant's own auto-start setting). The Spotify volume slider sets that speaker's volume. When Spotify stops, Music Assistant stops the speaker after 60 s.
- Limits: no track info or artwork in Music Assistant, no control from Music Assistant back to Spotify, and 3-4 s of delay on Cast speakers (much less on native Sendspin speakers).
- Requirements: Music Assistant 2.10+ with the Sendspin provider and the Sendspin Source plugin, and a Spotify Premium account.

## Documents

- [docs/DECISIONS.md](docs/DECISIONS.md): prior art, decisions, risks
- [docs/PLAN.md](docs/PLAN.md): architecture and phased plan
- [docs/TESTING.md](docs/TESTING.md): test results per phase
- [docs/MAINTENANCE.md](docs/MAINTENANCE.md): workflows, releasing, merging upstream
- [spike/](spike/): the throwaway Sendspin source test client used in Phase 0

## Branches

- `main` mirrors upstream (`hassio-addons/app-spotify-connect`), so syncing the fork is a fast-forward.
- `bridge` holds all the changes in this fork.

## Credits and licence

- Upstream app © 2018-2026 Franck Nijhof, MIT. See [LICENSE.md](LICENSE.md).
- [librespot](https://github.com/librespot-org/librespot) (MIT).
- [aiosendspin](https://github.com/Sendspin/aiosendspin) (Apache-2.0).
- `spike/state.py` is copied from [sendspin-jack-bridge](https://github.com/Sendspin/sendspin-jack-bridge) (Apache-2.0), and `spike/source_spike.py` is adapted from it.

This fork's own changes are MIT as well. It is not affiliated with Spotify, Home Assistant, the Open Home Foundation or Music Assistant.
