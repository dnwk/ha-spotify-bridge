# Spotify Bridge: Maintenance

## Branches

- `main` mirrors upstream `hassio-addons/app-spotify-connect`. Never commit to it.
- `bridge` is the default branch and holds all of the fork's changes.

## GitHub Actions

| Workflow | When | What |
|---|---|---|
| `ci.yaml` | push / PR to `bridge` | ruff + pytest (Python 3.14, Linux) and shellcheck on the s6 scripts |
| `build.yaml` | push to `bridge` touching `spotify_bridge/**` | builds `amd64` (ubuntu-24.04) and `aarch64` (ubuntu-24.04-arm) natively, pushes `ghcr.io/dnwk/<arch>-spotify-bridge:<version>`. Docker layers are cached in the GitHub Actions cache, so the librespot compile only reruns when its layer changes. |
| `upstream-sync.yaml` | Mondays 06:17 UTC, or by hand | fast-forwards `main` to upstream, then opens a PR `upstream-sync/<date>` into `bridge`. If the merge conflicts, it opens an issue instead. |

Repository settings this relies on:
- Actions enabled, with allowed actions limited to GitHub-owned ones plus `docker/*`. Upstream's workflows on `main` call `hassio-addons/workflows`, which this policy blocks, so they cannot run here.
- Default branch `bridge`.
- Issues enabled.
- GHCR packages `amd64-spotify-bridge` and `aarch64-spotify-bridge` are **public**, so Home Assistant can pull them without credentials.

## Releasing a version

1. Bump `version:` in `spotify_bridge/config.yaml` (for example `0.1.1`) and add an entry to `spotify_bridge/CHANGELOG.md` (HA shows it in the update dialog).
2. Push to `bridge`. Wait until **Build images** is green for both architectures. The image tag is the version.
3. In Home Assistant: Settings → Apps → Spotify Bridge → **Update**. HA pulls the image; nothing is compiled on the HA machine.
4. For a release (not a `-dev` build), tag it `bridge-v<version>` and create a GitHub release from the tag: `gh release create bridge-v0.1.1 --target bridge --notes-file <notes>`. The `bridge-` prefix keeps the fork's tags apart from upstream's `v0.x.y` tags (upstream already has `v0.1.0` to `v0.19.0`).

Never re-use a version number for different code. HA only pulls when the version changes.

## Merging upstream

Upstream's changes are mostly dependency bumps from Renovate (Alpine packages, the base image, librespot).

1. Review the weekly `upstream-sync/<date>` PR.
2. Run **CI** on that branch by hand. PRs opened by GitHub Actions do not trigger workflows.
3. Merge it, then bump `version:` so a new image is built.

If the bot opened an issue instead (conflict), do it locally:

```bash
git fetch upstream
git switch bridge
git merge upstream/main
```

Resolve the conflicts, then push. Typical conflicts:
- `spotify_bridge/Dockerfile` package pins next to the lines this fork removed (PulseAudio) or added (Python). Keep the fork's lines and take upstream's new versions.
- `spotify_bridge/config.yaml`: keep the fork's `name`, `slug`, `url`, `image`, options and schema.

## Local development

- Tests on Windows: `uv run --python 3.12 --with pytest --with aiosendspin==10.3.0 --with aiomqtt==2.5.1 --no-project python -m pytest -q` in `spotify_bridge/bridge`. The FIFO and Unix-socket tests are skipped on Windows; CI runs them.
- Image build: `docker build --build-arg BUILD_ARCH=amd64 -t local/spotify_bridge:dev spotify_bridge`.
- `spotify_bridge/bridge/tests/live_ma_source.py` tests the Sendspin source against a real Music Assistant from any PC. Afterwards, unpair the test device and remove it in MA.
