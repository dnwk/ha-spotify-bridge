# Spotify Bridge: Test Log

Results from the Phase 0 checks in [PLAN.md](PLAN.md). Risk and decision IDs refer to [DECISIONS.md](DECISIONS.md).

> This repo will be public. Keep account IDs, device IDs, session IDs, hostnames, IPs and tokens out of this file.

## Phase 0, check 1: librespot login with the owner's account (R1). **PASS** (2026-11-12)

**Setup:** the stock Spotify Connect add-on v0.19.0 (librespot 0.8.0, PulseAudio sink to the Dummy Output), on HAOS 18.4 (qemux86-64 VM), Core 2026.11.1, Supervisor 2026.11.0. The add-on was started by hand, with Start on boot left at manual.

**Steps:** started the add-on. The owner picked "Home Assistant" in the Spotify app and played a track for about 30 s, then switched away. The add-on was then stopped.

**Log (identifiers removed):**

```
19:34:13 librespot 0.8.0 … Using PulseAudioSink with format: S16
19:34:57 librespot_core::session  Connecting to AP "ap-….spotify.com:4070"
19:34:57 librespot_core::session  Authenticated as '<id>' !
19:34:58 librespot_connect::spirc active device is <…> with session <…>
19:34:58 librespot_playback::player Loading <track> with Spotify URI <spotify:track:…>
19:34:58 librespot_playback::player <track> (239853 ms) loaded
19:35:28 librespot_connect::spirc device became inactive
```

**Result:**
- The account (Premium, created before Dec 2024) authenticates with librespot 0.8.0 through zeroconf discovery, with no `access_token` needed.
- A track loads and decodes. Playback ran for about 30 s until the owner switched devices.
- **R1 is closed. D3 (librespot) stands.**

**Notes for later phases:**
- Spotify picked up the device about 44 s after librespot started (zeroconf discovery plus the user's action). Allow for this delay in startup tests.
- The `couldn't load context info … type: Default` warnings are harmless. They appear when playback is started from a single track rather than a playlist or album.
- Credentials are now cached in the **stock** add-on's `/data/system-cache`. The fork has its own slug and `/data`, so it will need one zeroconf selection from the Spotify app on its first run.
- After the test, the add-on state is: stopped, boot = manual (checked 19:35:36 UTC).

## Phase 0, check 2: Sendspin source spike into MA (D2). **PASS** (2026-11-12)

**Setup:**
- `spike/source_spike.py` runs on the Windows PC (Python 3.12 venv via uv, aiosendspin 10.3.0). It is adapted from Sendspin/sendspin-jack-bridge.
- It is a **client-initiated** connection to MA's Sendspin server (`ws://<ma-host>:8927/sendspin`, TCP 8927). Because the client dials out, no inbound firewall rule is needed on the client side.
- Roles: `source@v1` with `line_sense: true`. Audio: PCM s16, 44.1 kHz, stereo, in 20 ms chunks.
- Test signal: a quiet 440 Hz tone with a 1 kHz beep on every even wall-clock second.
- `control.txt` switches the line-sense signal between present and absent.
- MA 2.10.9 with the Sendspin player provider and the Sendspin Source plugin (alpha).

**Timeline (UTC):**

| Time | Event |
|---|---|
| 19:43:05 | Client connected, admitted and time-synced in < 1 s. While unpaired, the source role is inactive and `send_source_signal` raises "Source role is not active". |
| — | MA → Settings → Players showed **"Spotify Bridge spike — This player requires setup → Start setup"**. |
| 19:43:45 | MA's setup started a dynamic pairing code exchange. The client printed a 6-digit code (`pairing_code_display`). |
| 19:44:07 | The code was entered in MA: **"All set!"**. The client logged `Paired … via dynamic_pairing_code` and reported signal = absent. MA now shows "This device is paired. The connection is encrypted and authenticated." |
| — | Player settings → **"Automatically play line-in on"** set to *Living Room Display* (config key `source_autostart_target`). |
| 19:45:09 | Signal → **present** |
| 19:45:13 | MA sent `server/command source start` (**3.7 s** after the signal). The client created a SourceCapture (codec PCM) and streamed. |
| 19:45:14 | HA `media_player.living_room_display` = **playing**, title "Sendspin Source (Spotify Bridge spike)", content `sendspin_source://audio_source/<client-id>`. The Cast device fetches a `.wav` stream from MA (port 8097). The owner **heard the tone**. |
| 19:45:44 | Signal → **absent** (the spike kept feeding tone; the real add-on would feed silence or nothing) |
| 19:46:44 | MA sent `source stop`, **exactly 60 s** later (the autostop rule). Living Room Display went back to idle, and its previous queue item came back. |
| 19:50:12 | The client was restarted. It **reconnected with the stored pairing (no code)** and was active immediately. |
| 19:50:41 | **Unpaired** from MA (player settings → advanced → Unpair). MA dropped the connection, and the client's pairing store now holds 0 records. |

**Result:**
- D2 path A works end to end on this MA: pairing, auto-start on a chosen target, autostop, and paired reconnect.
- **D2 is confirmed.**

**Not measured:** end-to-end delay. The owner chose to skip it. MA 2.10.9's Sendspin Source plugin exposes no latency setting in its config (only `log_level`). Measure it in Phase 2 with real music.

**Findings that change the design:**
1. **Pairing UX:** a headless add-on must show the pairing code somewhere the user can see it. The add-on log works but is clunky.
   - Options: a persistent notification in HA (`persistent_notification.create` through `homeassistant_api`), or `static_pairing_code` (a code set in the add-on options and typed into MA).
   - Phase 2 should offer both. Default: a static code from the options, plus a log line.
2. **The pairing window must be open while unpaired.** The spike calls `open_pairing_window()` at startup, which acts as the "gesture". The add-on should do the same (only while unpaired).
3. **No signal before pairing.** `send_source_signal` raises until the source role is active, so the bridge must retry or queue the signal state until it is paired.
4. **Autostop takes 60 s.** After pausing in Spotify, the speaker stays "playing" (silence) for 1 minute, so a resume within 60 s continues seamlessly. On `session_disconnected` (another device chosen in Spotify), the bridge should also send signal absent. This is accepted as R4.
5. **Ghost player:** after a client disconnects, aiosendspin keeps it for `CLIENT_CLEANUP_DELAY = 180 s`, and MA shows it as available for that time. MA 2.10.9 has no "Remove" in the UI for Sendspin players. A paired client can be **unpaired** only while connected (advanced settings). The leftover player config is removed with `config/players/remove` after the 180 s.
6. **Identity persistence:** `identity.key` + `pairings.json` (aiosendspin `FileClientPairingStore`) must live in the add-on's `/data`. Losing them means re-pairing. Never commit them (the spike's `.gitignore` covers `.state/`).

**Cleanup (verified 2026-11-12 19:54 UTC):**
- Spike process stopped.
- Unpaired on both sides.
- The MA player unregistered on its own at about 190 s.
- `config/players/remove` deleted its config, including the `source_autostart_target`. `config/players/get` now errors, and the player list no longer contains it.
- Living Room Display is idle.
- MA settings are otherwise unchanged. Nothing changed in HA.
- The spike code stays in `spike/` for reference in Phase 2. Its `.state/` holds a now-unused identity key (git-ignored).

## Phase 1: the fork running on the test HA. **PASS** (2026-11-12)

**Build and install:**
- Local amd64 build with Docker Desktop: about 2.5 min, 145 MB.
- Then HA added the repository `https://github.com/dnwk/ha-spotify-bridge#bridge` (slug `2f193555_spotify_bridge`) and built the image on the HAOS 18.4 VM in **14.5 min**.
- Supervisor warning: "uses build.yaml which is deprecated". The file comes from upstream; we follow upstream on this.

**Start-up:** `cont-init` created the FIFO, then `librespot` and `bridge` started.
- librespot: `volume control: Fixed`, `Using StdoutSink (pipe) with format: S16`.
- Bridge: listening for events, reading the FIFO.
- The app runs with `host_network: true`, `audio: false`.

**Live test** (the owner picked "Home Assistant" in the Spotify app; track names left out on purpose):

| Local time | Bridge log |
|---|---|
| 15:38:42 | librespot: connecting to the access point, `Authenticated`, active device |
| 15:38:43 | `Player: connected`, `Spotify volume: 50%`, then `Player: playing, '<track 1>' by <artist>`, **`Signal present`** |
| 15:38:48 – 15:39:03 | `Audio flowing: 250 chunks in 5 s` every 5 s (**exactly real time**), loudest −12 to −17 dBFS |
| 15:39:06 | next track loaded: `Player: playing, '<track 2>'` (the signal stays present across the track change) |
| 15:39:11 | `Player: paused`, **`Signal absent`** |
| 15:39:16 | `Player: playing`, **`Signal present`** |
| 15:39:30 | `Player: paused`, `Signal absent` |
| 15:39:39 | librespot: `device became inactive` (the owner switched device), then `Player: idle` |

**Result:**
- librespot → FIFO → bridge works on the real HA, with real Spotify audio, track changes, and pause/resume.
- The reader holds librespot to real time: 250 chunks per 5 s, with no starving while playing.

**Bug found and fixed:** after `session_disconnected`, librespot also sends `stopped`. The state machine went idle → connected. It now stays idle (new test `test_stopped_after_disconnect_stays_idle`). This had no effect on the signal, which stayed absent.

**After the test:** Spotify Bridge is stopped with boot set to `manual`. The stock Spotify Connect app is stopped with boot `manual` (unchanged).

## Phase 2: Spotify → Music Assistant → speaker on the test HA. **PASS** (2026-11-12)

**PC live test first** (`spotify_bridge/bridge/tests/live_ma_source.py`, a tone generator instead of librespot):
- **Static 8-digit code** pairing works, but only after enabling `static_pairing_code_enabled` in the client's pairing config. Without it, aiosendspin offers only `pairing_psk`, and MA asks for a long "pairing token". Fixed in `sendspin_source._apply_static_code`.
- Signal present → MA `source start` in **3.9 s**.
- Pause 15 s then resume: the same stream continues (no new start).
- Signal absent → `source stop` after exactly **60 s**.
- Unpair in MA → the connection drops → the bridge reconnects after 2 s, logs `No longer paired`, and offers pairing again.
- The test device was then removed (`config/players/remove`). The unpaired player was unregistered right away this time, with no 180 s wait.

**On HA:**
- After the push, `store/reload` + `rebuild` took **31 s** (the librespot layer was cached). The Supervisor picked up the new options and `homeassistant_api: true`. The app connected to MA at `ws://localhost:8927/sendspin` with no configuration.
- **Dynamic code pairing:** Start setup in MA → the bridge logged `pairing code: XXX-XXX` and HA showed the notification "Spotify Bridge: Music Assistant pairing code" → code entered → "All set!". The notification was dismissed automatically when pairing ended.
- Auto-start target set to Living Room Display (Nest Hub, Cast).

**Live Spotify test (local time, track names left out):**

| Time | Bridge log |
|---|---|
| 16:35:25 | librespot `Authenticated` (the owner picked "Home Assistant" in Spotify) |
| 16:35:27 | `Player: playing`, `Signal present`, `Told Music Assistant: signal present` |
| 16:35:30 | `Music Assistant requested source start`, `Streaming to Music Assistant (pcm)` (**3 s**) |
| — | The owner **heard it on Living Room Display**. HA `media_player.living_room_display` showed "Sendspin Source (Spotify (Home Assistant))". |
| 16:35:50 | `Player: paused`, `Signal absent` |
| 16:35:58 | `device became inactive` → `Player: idle` (the Phase 1 fix: no bounce to "connected") |

**Notes:**
- A leftover MA queue item from the PC test ("Sendspin Source (Spotify Bridge live test)") was resumed from the MA/HA play button and played silence ("buffering" on the Nest Hub) until it was stopped. That's harmless, but **a test source's queue item outlives the device**. When removing a test device, also stop the players that used it.
- librespot logged a `WARN … dealer … failure during data parsing for hm://collection/…`. It's unrelated to playback and is a known librespot quirk.
- **Not measured yet:** end-to-end delay. Not done yet: volume sync (Phase 3).
