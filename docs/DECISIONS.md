# Spotify Connect → Music Assistant Bridge: Decision Record

Working name: **Spotify Bridge** (add-on slug `spotify_bridge`). It is a fork of [hassio-addons/app-spotify-connect](https://github.com/hassio-addons/app-spotify-connect).
Status: **Draft, step 1 of the project.** Decisions marked *Proposed* need the owner's OK before Phase 1 starts.
Date: 2026-11-12

> Terminology: Home Assistant 2026.11 calls add-ons **Apps** (Settings → Apps). This document says "add-on", meaning the same thing.

## Goal

Keep a Spotify Connect device that the Spotify app can select ("Home Assistant", or a name you choose). Instead of playing into the HA host's sound card, send the audio into **Music Assistant (MA)**, so you can choose which speaker actually plays it: a Cast display or TV, an HA Voice PE, a sync group, and so on.

Out of scope: Spotify Free accounts (unless the engine choice in D3 changes), video, and controlling Spotify from HA dashboards (HA's own Spotify integration already does that).

## Why the stock add-on can't do this today (verified 2026-11-12)

- The upstream add-on (v0.19.0, MIT) builds **librespot 0.8.0** with only the `pulseaudio-backend` feature. Its run script passes no backend or device option, so audio goes to the Supervisor's PulseAudio default sink.
- This HA runs **HAOS 18.4 as a VM (qemux86-64)**. Its only audio output is `auto_null` ("Dummy Output"), so the stock add-on plays silence. That is why it was stopped and set to manual start on 2026-11-12.
- The add-on has no setting for an output target. It is ~40 lines of bash around one `librespot` command.

---

## Prior art survey (November 2026)

| Project | What it is | Relevance |
|---|---|---|
| **Upstream add-on** [app-spotify-connect](https://github.com/hassio-addons/app-spotify-connect) v0.19.0 | librespot 0.8.0 on `ghcr.io/hassio-addons/base:21.0.11`. Options: `name`, `bitrate`, `autoplay`, `initial_volume`, `access_token`. Credentials cached in `/data/system-cache`. | **Fork base.** Small and easy to keep in sync. It only needs a different audio backend, plus something to carry the audio into MA. |
| **[librespot](https://github.com/librespot-org/librespot)** 0.8.0 (2025-11-10, MIT) | Rust Spotify Connect client | Has `--backend pipe` (to a FIFO or stdout), `--backend subprocess`, and `--onevent <program>`. The hook fires on `session_connected`, `playing`, `paused`, `stopped`, `track_changed`, `volume_changed`, `session_client_changed` and more (verified in `src/player_event_handler.rs`). **There is no local control API**, so MA can't pause Spotify through it. |
| **MA built-in "Spotify Connect" plugin** (beta; [code](https://github.com/music-assistant/server/tree/2.10.9/music_assistant/providers/spotify_connect)) | One Spotify Connect device per MA player selected in **Connected players**. Audio goes into MA, and transport and volume are passed back to Spotify. Two engines: **Spotify Soloist** (official, API key, Free or Premium, lossless) and **go-librespot** (community). | **Already does almost exactly this goal with no code.** It is available on this MA 2.10.9 but not installed. The main difference from this project is that you pick the speaker in the Spotify app's device list, rather than having one device whose speaker is chosen in MA/HA. |
| **[go-librespot](https://github.com/devgianlu/go-librespot)** v0.10.5 (2026-10-16, GPL-3.0) | Go Spotify Connect client with prebuilt binaries for amd64/arm64 | Has a local REST control API (`/player/pause`, `/resume`, `/next`, `/volume` …) and an `/events` WebSocket. Its pipe output is `s16le` to stdout. MA's plugin uses it. MA documents: **"only works with Premium-family accounts created before December 2024"**. |
| **Spotify Soloist** (official headless Linux client, Aug 2026) | Spotify's own Connect daemon | Works with every account type and survives protocol changes. But it needs a personal API key, is downloaded from Spotify's CDN after the user consents, **expires 90 days after its build date**, and only plays into PulseAudio. MA handles all of this. Re-implementing it in an add-on is significant work and probably not allowed to be redistributed in an image. |
| **MA "Sendspin Source" plugin** (alpha, built-in; installed on this MA) | Shows paired Sendspin clients that have the **source** role as **Live Inputs** in MA, playable on any player or group. | **The cleanest way to get our audio into MA.** It handles clock drift and latency (`AsrcSourceBridge`, soxr), keeps the stream alive with silence, and **auto-starts on a chosen target player** when a client with `line_sense` reports a signal, stopping 1 min after the signal goes away. |
| **[aiosendspin](https://pypi.org/project/aiosendspin/)** 10.3.0 (Apache-2.0, Python ≥ 3.12) | Sendspin protocol library | Includes the *client* source role: `SendspinClient.create_source_capture()` with `SourceCapture.feed()`, plus the `line_sense` feature and `SourceStatePayload.signal`. |
| MA "AirPlay Receiver" plugin / [ha-airplay-bridge](../../ha-airplay-bridge/docs/DECISIONS.md) | The same "receiver → MA/HA player" pattern for AirPlay | Share design and maybe code (HTTP stream fallback, Sendspin client handling). |

---

## Options compared (pros / cons)

✅ marks the option chosen or proposed.

### D1. Overall approach

| Option | Pros | Cons |
|---|---|---|
| 1. Use MA's built-in Spotify Connect plugin (no code) | Zero development. One device per player and group. Two-way transport and volume. Soloist engine works for every account type. Maintained by the MA team. | Beta. Speaker choice happens by picking a *different device* in Spotify, so you get N devices instead of one. Soloist needs an API key and a CDN download. |
| ✅ 2. Fork the upstream add-on and feed MA as a **Sendspin source** | One Spotify device, with the speaker chosen in MA/HA. Small diff from upstream. Independent of the MA Spotify plugin. Learning that carries over to the AirPlay bridge. | We maintain it. librespot account restriction (R1). No pause from MA back to Spotify with librespot (D3). Depends on the alpha Sendspin Source plugin. |
| 3. Fork and send an HTTP stream via `media_player.play_media` | Works with any HA player, even without MA. Simplest code. | 2–8 s extra delay. Shows as a "radio stream" in MA (no metadata or controls). No silence handling. |
| 4. Contribute a "single device, selectable target" mode to MA's plugin | Smallest long-term maintenance. Helps others. | Upstream review and timing. Python inside MA, not an add-on. |

### D2. How audio gets into Music Assistant

| Option | Pros | Cons |
|---|---|---|
| ✅ A. Sendspin client with the **source** role (+ `line_sense`) | A native MA Live Input. Auto-starts on a configured target. Drift correction and silence-hold are done by MA. Can be moved to any player or group in MA. | Alpha plugin and protocol at RC1. Needs pairing. Only works with MA. |
| ✅ B. HTTP stream + `media_player.play_media` on an MA (or any HA) player (fallback, Phase 3) | Works today on any player. No pairing. | Delay, no metadata in MA, and a fresh "radio" item each session. |
| C. PulseAudio null sink inside the add-on, captured by MA | — | MA can't read another container's PulseAudio. Rejected. |

### D3. Spotify engine inside the fork

| Option | Pros | Cons |
|---|---|---|
| ✅ librespot 0.8.0 (keep upstream's) | Smallest diff, so upstream updates merge cleanly. `--backend pipe` + `--onevent` cover audio and state. MIT. | No local control API (MA can't pause, skip or seek in Spotify). Premium only. Probably the same pre-Dec-2024 account restriction as go-librespot (R1). Rust build takes ~15–25 min per arch in CI. |
| go-librespot 0.10.x | REST control API + events WebSocket, so pause/next from MA works. Prebuilt binaries mean fast builds. Proven by MA. | Replaces the engine, so it's barely a "fork" any more. GPL-3.0 binary (fine as a separate program). Same account restriction. |
| Spotify Soloist | Official. Free accounts. Lossless. | API key, CDN download with consent, 90-day expiry, PulseAudio-only output. Redistribution terms are unclear. MA already does all of this. |

### D4. Number of Spotify devices

| Option | Pros | Cons |
|---|---|---|
| ✅ One device, speaker chosen in MA/HA (v1) | Matches the goal: one "Home Assistant" entry in Spotify. | You can't pick the speaker from the Spotify app itself. |
| A list of devices, each with a fixed default target (v2, optional) | You can pick the room in Spotify too | Repeats what MA's own plugin does. Needs one librespot and one Sendspin client per device. |

### D5. Choosing the target speaker

| Option | Pros | Cons |
|---|---|---|
| ✅ MA's Sendspin Source **autostart target** (set in MA under the device's settings) + moving the Live Input by hand in MA | No code. Supports groups and stereo pairs. | Changing the default means opening MA settings. |
| ✅ HA `select` entity (Phase 4) listing MA players; on change, start the Live Input there | You can switch speakers from a dashboard or automation | Needs to confirm that HA's MA integration can play an AudioSource item (open question 4). |
| Add-on option `target_player` | Simple | Restart needed to change it. Clumsy. |

### D6. Volume

| Option | Pros | Cons |
|---|---|---|
| ✅ librespot `--volume-ctrl fixed` (full-scale PCM). The Spotify slider is mirrored to the current MA target's volume through HA `media_player.volume_set` (option `volume_sync`, on by default). | Best quality. The Spotify slider works. | Changes the speaker's own volume. Needs `homeassistant_api` and a way to find the current target. |
| librespot softvol (upstream default) | No extra code | Quieter and lower quality at low volume. Two volume controls stacked. |

### D7. Bridge runtime

| Option | Pros | Cons |
|---|---|---|
| ✅ Python 3.12+ asyncio service (aiosendspin, aiohttp) under s6, next to librespot | aiosendspin only exists in Python. Same stack as MA and the AirPlay bridge. | A larger image than pure bash. |
| Bash + ffmpeg only (no Sendspin) | Tiny | Can only do Path B. |

### D8. Repository, licence, distribution

| Option | Pros | Cons |
|---|---|---|
| Private duplicate (`git clone` + push to a new private repo), keeping `upstream` as a remote | Private until it works. Upstream can still be merged. | Not a GitHub "fork" link, so no one-click PRs upstream. |
| ✅ **Public GitHub fork** | Easy upstream PRs and syncing ("Sync fork" button). Visible. | Public from day one, so no secrets in the repo, ever. Images on GHCR are public too. |

---

## Decisions

### D1. Fork the add-on and feed Music Assistant as a Sendspin source. *Decided by the owner on 2026-11-12*

The owner chose **one** Spotify device, with the speaker chosen in MA/HA, over MA's per-speaker devices. MA's built-in plugin is no longer the plan. It may still be used once in Phase 0 as a delay baseline (optional).

**Revisit only if:** R1 shows librespot can't log in with the owner's account. In that case the fallback is MA's plugin with the Soloist engine, which means per-speaker devices.

### D2. Audio path: Sendspin source first, HTTP `play_media` as a fallback. *Decided: confirmed by the Phase 0 spike on 2026-11-12 (pairing, auto-start, autostop and reconnect all work; see TESTING.md)*

- **Path A (Phase 1–2):** the bridge is a Sendspin **client** (roles: `source@v1` with `line_sense`, optionally `metadata`). It advertises `_sendspin._tcp` and is paired once in MA. MA shows it as the Live Input "Spotify (Home Assistant)".
  - librespot `playing` → `signal: present` → MA auto-starts it on the target.
  - `paused`/`stopped` → `signal: absent` → MA stops it after 1 min.
  - The bridge streams PCM only while MA has sent `start` (server-initiated, per spec).
- **Path B (Phase 3, option `output: media_player`):** an aiohttp stream at `http://<host>:<port>/spotify.flac`. On `playing`, the bridge calls `media_player.play_media` on a configured entity through `http://supervisor/core/api`.

### D3. Keep librespot 0.8.0, change only the backend. *Decided by the owner on 2026-11-12: two-way control is not needed*

- Build features: `native-tls with-libmdns`, dropping `pulseaudio-backend`. Run with `--backend pipe --device /run/spotify/pcm.fifo --format S16 --volume-ctrl fixed --onevent /usr/bin/spotify-event`. The output is 44.1 kHz stereo s16le.
- `spotify-event` is a 5-line script that forwards `PLAYER_EVENT` and the track and volume variables to the bridge over a Unix socket.
- **Limitation, by design:** MA can stop *its* playback, but it can't pause Spotify. The Spotify app keeps "playing" into silence until it is paused there.
- **Switch to go-librespot if** you want pause/next from MA or HA (its REST API makes this a ~1 day change behind the same bridge interface).

### D4. One Spotify device in v1. *Decided*

The option `name` (default "Home Assistant") stays as it is upstream. A `devices:` list is a Phase 5 option.

### D5. The target is chosen in MA; an HA `select` comes later. *Decided (the owner confirmed on 2026-11-12 that the dashboard picker is not needed in v1)*

The default target is MA's autostart target for this Sendspin source. Moving playback to another speaker is done in MA, or later with the HA `select` (Phase 4).

### D6. Fixed-level PCM; Spotify volume is mirrored to the target. *Decided*

The add-on needs `homeassistant_api: true`. Volume events from Spotify are debounced (250 ms) and applied to the MA player entity currently playing this source.

### D7. Add-on container. *Decided*

Changes from upstream:

- `host_network: true` stays (zeroconf for Spotify and Sendspin).
- `audio: true` is **removed**.
- `homeassistant_api: true` is added.
- `init: false` and s6 services stay, with services `librespot` + `bridge`. The upstream `finish` script (halt on crash) is kept for librespot and also added for the bridge.
- Base image: keep `ghcr.io/hassio-addons/base` and add `python3` + a venv. Architectures: `aarch64`, `amd64`.
- New options:

```yaml
name: Home Assistant        # upstream
bitrate: 160                # upstream (96|160|320)
autoplay: true              # upstream
initial_volume: 50          # upstream
access_token: ""            # upstream
output: sendspin            # sendspin | media_player
media_player: ""            # entity for output=media_player
volume_sync: true
sendspin_name: ""           # defaults to "Spotify (<name>)"
log_level: info
```

### D8. Public GitHub fork, MIT, own slug. *Decided by the owner on 2026-11-12*

- A **public GitHub fork** of hassio-addons/app-spotify-connect under `dnwk`, renamed to `dnwk/ha-spotify-bridge` after forking. The fork link stays, and `upstream` = hassio-addons/app-spotify-connect for merges.
- The planning docs live in `docs/` on the `bridge` branch.
- Work happens on a `bridge` branch. `main` tracks upstream, so syncing stays a fast-forward. `bridge` gets merged from `main` monthly (R8).
- A `repository.yaml` is added at the root, so HA can install it as an add-on repository. The slug `spotify_bridge` and name "Spotify Bridge" avoid clashing with the stock add-on, which stays installed and stopped.
- MIT (as upstream; keep Franck Nijhof's copyright notice). librespot is MIT; aiosendspin is Apache-2.0.
- **Public repo hygiene:** no tokens, hostnames, IPs or personal data in commits. Spotify credentials only ever live in the add-on's `/data` on the HA box.
- Images are built by GitHub Actions (`home-assistant/builder`) and pushed to **public** GHCR packages. For early phases, the add-on is built locally on the HA box from `/addons/local`.
- Upstream's CI workflows (`deploy.yaml`, `labels.yaml`, `release-drafter.yaml`) target the hassio-addons org. Disable them in the fork and replace them with our own build workflow.

---

## Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | **Spotify account restriction.** MA documents that go-librespot works only with Premium-family accounts **created before Dec 2024**. librespot uses the same reverse-engineered protocol, so assume the same. | Phase 0 step 1: log in with the stock add-on (already installed) and confirm playback starts (logs show `playing`). If it fails, stop and use MA's plugin with Soloist. |
| R2 | The Sendspin Source plugin and protocol are **alpha / RC1** and may change. | Pin aiosendspin. Keep Path B as a fallback. Retest on each MA update. |
| R3 | **Pairing.** The source role only activates on paired connections. | Document the pairing steps. Persist the client identity and keys in `/data`. |
| R4 | Pause in the Spotify app → MA keeps the player "on" for 1 min (silence-hold). Pause in MA → Spotify keeps going. | Accept for v1 and document it. go-librespot (D3) fixes the reverse direction. |
| R5 | **Delay**: Spotify buffer + MA's target latency + player buffer. | Measure in Phase 0. Tune the Sendspin Source latency setting. |
| R6 | Two Spotify Connect devices if the MA plugin is also enabled, causing confusion. | Use one approach or the other. Phase 0 removes whichever loses. |
| R7 | Rust build time and size in CI (librespot built from crates). | Cache cargo in CI, or switch to go-librespot's prebuilt binaries. |
| R8 | Upstream drift (frequent Renovate bumps upstream). | Keep our changes in new files where possible. Merge upstream monthly. |

## Open questions for the owner

1. ~~One device or per-speaker devices?~~ **Answered 2026-11-12: one device (fork). D1 decided.**
2. ~~Spotify account?~~ **Premium, created before Dec 2024** (owner, 2026-11-12). **R1 closed:** librespot login and playback were confirmed in Phase 0 check 1 (see [TESTING.md](TESTING.md)).
3. ~~Pause/skip back to Spotify?~~ **Not needed.** D3 = librespot.
4. ~~HA dashboard picker in v1?~~ **Later** (Phase 4).
5. ~~Repo?~~ **Public GitHub fork.** D8 updated.

All open questions are answered. Next: Phase 0.
