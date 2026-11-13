# Spotify Bridge

A fork of the Home Assistant Community app "Spotify Connect". It is a Spotify
Connect device ("Home Assistant" by default) that plays through **Music
Assistant** instead of this machine's own sound output: Music Assistant
decides which speaker (or group) plays it.

**Work in progress.** Requirements: Music Assistant 2.10+ (as an app on this
Home Assistant) with the **Sendspin** player provider and the **Sendspin
Source** plugin, and a Spotify Premium account.

## Installation

1. Add `https://github.com/dnwk/ha-spotify-bridge#bridge` under
   Settings > Apps > (menu) > Repositories, then install "Spotify Bridge".
   Home Assistant builds it locally (about 15 minutes).
1. Optional: set a `pairing_code` (8 digits) in the Configuration tab.
1. Start the app and pair it with Music Assistant (below).
1. In the Spotify app, pick the device named like the `name` option.

## Pairing with Music Assistant (once)

1. In Music Assistant open Settings > Players. "Spotify (Home Assistant)"
   shows **This player requires setup**. Click **Start setup**.
1. Enter the code:
   - with `pairing_code` set: type those 8 digits;
   - without it: a 6-digit code appears as a Home Assistant notification
     (and in this app's log). It is valid for about 2 minutes.
1. Open the new player's settings in Music Assistant and choose a speaker
   under **Automatically play line-in on**. Playback from Spotify now starts
   there automatically. You can move it to another speaker or group in Music
   Assistant at any time.

The pairing is stored in the app's data, so it survives restarts and updates.
To pair again, unpair in Music Assistant (player settings, advanced) while the
app is running.

## Choosing the speaker

Two ways, pick one:

- **In Music Assistant:** the input's setting **Automatically play line-in
  on** decides where Spotify starts. Keep the **Speaker** entity (below) on
  "Music Assistant setting".
- **From Home Assistant:** the app adds a **Speaker** select entity (device
  "Spotify Bridge (<name>)", via MQTT/Mosquitto) listing your Music Assistant
  speakers and groups. Choose one there, from a dashboard or an automation.
  The bridge starts Spotify on it when you press play, and moves it when you
  change the selection mid-song. In this mode set **Automatically play
  line-in on** to **Off** in Music Assistant, otherwise both start a speaker.

## Behaviour to know

- **Delay** after pressing play or pause in Spotify depends on the speaker:
  about 3-4 seconds on Google Cast speakers (they buffer several seconds),
  much shorter on native Sendspin speakers such as Home Assistant Voice PE.
- **Volume:** the Spotify volume slider sets the volume of the speaker that
  plays it. When you first pick the device, the speaker keeps its own volume.
  Changing the speaker volume elsewhere does not move the Spotify slider.
- Pausing in Spotify keeps the speaker "playing silence" for 60 seconds, so a
  quick resume continues seamlessly; after that Music Assistant stops it.
- Stopping the player in Music Assistant does not pause Spotify.
- Music Assistant shows "Sendspin Source (Spotify (<name>))" instead of the
  song title: the Sendspin source role carries audio only.

## Configuration

**Note**: _Remember to restart the app when the configuration is changed._

Example app configuration:

```yaml
log_level: info
name: Home Assistant
bitrate: 320
initial_volume: 50
autoplay: true
music_assistant_url: ws://localhost:8927/sendspin
pairing_code: "12345678"
volume_sync: true
speaker_select: true
```

**Note**: _This is just an example, don't copy and paste it! Create your own!_

### Option: `log_level`

The `log_level` option controls the level of log output by the app and can
be changed to be more or less verbose, which might be useful when you are
dealing with an unknown issue. Possible values are:

- `trace`: Show every detail, like all called internal functions.
- `debug`: Shows detailed debug information.
- `info`: Normal (usually) interesting events.
- `warning`: Exceptional occurrences that are not errors.
- `error`: Runtime errors that do not require immediate action.
- `fatal`: Something went terribly wrong. App becomes unusable.

Please note that each level automatically includes log messages from a
more severe level, e.g., `debug` also shows `info` messages. By default,
the `log_level` is set to `info`, which is the recommended setting unless
you are troubleshooting.

Setting the `log_level` to `debug` will also turn on debug mode on
librespot.

### Option: `name`

The name of your device (the Spotify Connect target), as shown on
the official Spotify clients.

### Option: `bitrate`

The bitrate Spotify should use. The higher, the better the sound quality,
however, the app consumes more data.

Valid values: `96`, `160` (default) or `320`.

### Option: `initial_volume`

Initial volume in % from 0-100. This setting takes effect when the app starts or
recovers from a crash.

### Option: `autoplay`

Whether Spotify should autoplay similar songs when reaching the end of the queue.

### Option: `music_assistant_url`

Where Music Assistant's Sendspin server listens. The default
`ws://localhost:8927/sendspin` works when Music Assistant runs as an app on
this Home Assistant.

### Option: `sendspin_name`

Name of the Live Input in Music Assistant. Defaults to `Spotify (<name>)`.

### Option: `pairing_code`

Optional fixed 8-digit code (for example `1234-5678`) to type into Music
Assistant when pairing. Leave it empty to get a one-time code as a
notification instead.

### Option: `volume_sync`

When on (default), the Spotify volume slider sets the speaker volume.

### Option: `speaker_select`

When on (default) and the Mosquitto broker app is installed, the app adds the
**Speaker** select entity described above.

### Option: `access_token`

When set, login to spotify account using this token. See
[librespot documentation](https://github.com/librespot-org/librespot/wiki/Options#access-token)
how to obtain one.

To change the token, set it to empty first, restart app and only then set the
new one.

## Known issues and limitations

- This app requires a Spotify Premium account.

## Changelog & Releases

This repository keeps a change log using [GitHub's releases][releases]
functionality.

Releases are based on [Semantic Versioning][semver], and use the format
of `MAJOR.MINOR.PATCH`. In a nutshell, the version will be incremented
based on the following:

- `MAJOR`: Incompatible or major changes.
- `MINOR`: Backwards-compatible new features and enhancements.
- `PATCH`: Backwards-compatible bugfixes and package updates.

## Support

Got questions?

You have several options to get them answered:

- The [Home Assistant Community Apps Discord chat server][discord] for app
  support and feature requests.
- The [Home Assistant Discord chat server][discord-ha] for general Home
  Assistant discussions and questions.
- The Home Assistant [Community Forum][forum].
- Join the [Reddit subreddit][reddit] in [/r/homeassistant][reddit]

You could also [open an issue here][issue] on GitHub.

## Authors & contributors

The original setup of this repository is by [Franck Nijhof][frenck].

For a full list of all authors and contributors,
check [the contributor's page][contributors].

## License

This fork's changes and the upstream app are MIT licensed (text below).
Bundled third-party software keeps its own licence:
[librespot](https://github.com/librespot-org/librespot) (MIT),
[aiosendspin](https://github.com/Sendspin/aiosendspin) (Apache-2.0),
[aiomqtt](https://github.com/empicano/aiomqtt) (BSD-3-Clause),
[paho-mqtt](https://github.com/eclipse-paho/paho.mqtt.python) (EPL-2.0 or EDL-1.0),
and their dependencies (aiohttp, cryptography, zeroconf and others).
This project is not affiliated with Spotify.

MIT License

Copyright (c) 2018-2026 Franck Nijhof

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

[app-badge]: https://my.home-assistant.io/badges/supervisor_addon.svg
[app]: https://my.home-assistant.io/redirect/supervisor_addon/?addon=a0d7b954_spotify&repository_url=https%3A%2F%2Fgithub.com%2Fhassio-addons%2Frepository
[contributors]: https://github.com/hassio-addons/app-spotify-connect/graphs/contributors
[discord-ha]: https://discord.gg/c5DvZ4e
[discord]: https://discord.me/hassioaddons
[forum]: https://community.home-assistant.io/t/home-assistant-community-add-on-spotify-connect/61210?u=frenck
[frenck]: https://github.com/frenck
[issue]: https://github.com/hassio-addons/app-spotify-connect/issues
[reddit]: https://reddit.com/r/homeassistant
[releases]: https://github.com/hassio-addons/app-spotify-connect/releases
[semver]: https://semver.org/spec/v2.0.0.html
