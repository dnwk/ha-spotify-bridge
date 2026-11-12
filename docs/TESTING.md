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
19:34:58 librespot_playback::player Loading <Light> with Spotify URI <spotify:track:…>
19:34:58 librespot_playback::player <Light> (239853 ms) loaded
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
