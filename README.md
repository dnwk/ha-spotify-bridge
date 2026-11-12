# Spotify Bridge for Home Assistant

A fork of the Home Assistant Community app [Spotify Connect](https://github.com/hassio-addons/app-spotify-connect) by Franck Nijhof.

The upstream app plays Spotify through the Home Assistant host's own sound output. This fork sends the audio into **[Music Assistant](https://music-assistant.io)** as a Sendspin **Live Input** instead. You keep one Spotify Connect device ("Home Assistant"), and you choose in Music Assistant which speaker actually plays it: Cast displays and TVs, Home Assistant Voice PE, sync groups, and so on.

> **Status: work in progress.** Phase 0 (de-risking) is done. Nothing is installable yet. Please use the [upstream app](https://github.com/hassio-addons/app-spotify-connect) if you want something that works today.

## How it will work

```
Spotify app ──Connect──▶ librespot (pipe backend) ──PCM──▶ bridge (Python, aiosendspin)
                                                              │ Sendspin source role + line-sense
                                                              ▼
                                            Music Assistant "Live Input" ──▶ any MA speaker / group
```

- **librespot 0.8.0** (as upstream) writes decoded audio to a FIFO and reports play, pause and volume events.
- The **bridge** is a paired Sendspin *source* client. When Spotify plays, it reports "signal present", and Music Assistant's **Sendspin Source** plugin starts it on the speaker you picked. When Spotify stops, Music Assistant stops the speaker after 60 s.
- Requirements: Music Assistant 2.10+ with the Sendspin provider and the Sendspin Source plugin, and a Spotify Premium account.

## Documents

- [docs/DECISIONS.md](docs/DECISIONS.md): prior art, decisions, risks
- [docs/PLAN.md](docs/PLAN.md): architecture and phased plan
- [docs/TESTING.md](docs/TESTING.md): Phase 0 results (librespot login, Sendspin source into Music Assistant)
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
