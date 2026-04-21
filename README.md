# Minecraft WebUI

Monitoring dashboard for Minecraft Java Edition servers, with Discord notifications and RCON console.

> 🇫🇷 [Version française](README.fr.md)

![Version](https://img.shields.io/badge/version-1.9.0-green)
![Docker](https://img.shields.io/badge/docker-compose-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

## Screenshots

| Dashboard | Players |
|---|---|
| ![Dashboard](docs/screenshots/screenshot-dashboard.png) | ![Players](docs/screenshots/screenshot-players.png) |

| Statistics | RCON Console |
|---|---|
| ![Stats](docs/screenshots/screenshot-stats.png) | ![Console](docs/screenshots/screenshot-console.png) |

## Features

- **Dashboard** — server status, latency, online players, server/VM uptime, system resources (CPU/RAM/Swap/Disk + network KB/s) in real time via SSE
- **Players** — connected players list with Minecraft skins; click a player → modal with UUID, skin type, cape; **Kick / Ban** (admin, RCON)
- **History** — connection/disconnection log persisted in SQLite (filters: 24h / 7d / 30d)
- **Statistics** — playtime per player, peak hours, CPU/RAM/Disk + network/disk I/O history 24h (Chart.js)
- **Logs** — last 100 lines of the server log with level coloring and real-time filter
- **Discord notifications** — embed with player skin sent on each join/leave
- **RCON console** — interactive terminal with a quick-reference command cheatsheet (admin)
- **Appearance** — server banner and favicon customizable from the UI (admin upload)
- **Theme** — dark / light toggle persisted in the browser (localStorage)
- **Config UI** — Discord webhook and RCON settings editable from the interface, password-protected
- **Push notifications** — browser push notifications (Web Push / VAPID) on player join/leave (Android, iOS 16.4+, desktop)
- **PWA** — installable as a Progressive Web App on mobile (Android/iOS)
- **Versioning** — version displayed in the footer (`web/VERSION`)

## Stack

| Service | Role |
|---|---|
| `web` | FastAPI + Jinja2 + Uvicorn |
| `discord-notifier` | Async polling + Discord webhooks |
| `caddy` | HTTPS reverse proxy |

## Requirements

- Docker + Docker Compose
- Minecraft Java server with `enable-status=true` in `server.properties`

> **Note**: the Logs page and server uptime detection require the Minecraft `latest.log` file to be accessible locally on the Docker host (via the `MC_LOG_PATH` setting). For a remote server, a network mount (NFS, sshfs…) is sufficient.

## Installation

```bash
git clone https://github.com/picardflo/minecraft_webui.git
cd minecraft_webui

cp .env.example .env
nano .env

docker compose up -d --build
```

## Configuration (.env)

```env
MC_HOST=your.minecraft.server.com   # Minecraft server address
MC_PORT=25565                        # Java port (default 25565)
MC_LOG_PATH=/srv/minecraft/server/logs/latest.log

ADMIN_PASSWORD=changeme              # Password for /settings and /console
SECRET_KEY=change-this-to-a-long-random-string

DOMAIN=localhost                     # Domain used by Caddy
```

## SSL / TLS

Three modes available, selected via `CADDYFILE` in `.env`:

### Mode 1 — Self-signed (default, LAN/local)

No extra configuration. Caddy generates a local certificate automatically.

```env
DOMAIN=mc.home.lan
# CADDYFILE not set → uses Caddyfile (tls internal)
```

> The browser will show a security warning the first time.

### Mode 2 — Let's Encrypt (public domain)

Ports 80 and 443 must be open and the domain must point to your IP.

```env
DOMAIN=mc.example.com
CADDYFILE=Caddyfile.letsencrypt
TLS_EMAIL=admin@example.com
```

### Mode 3 — Existing certificate (wildcard, corporate…)

Place `fullchain.pem` and `privkey.pem` in the `./certs/` folder.

```env
DOMAIN=mc.home.lan
CADDYFILE=Caddyfile.custom
```

## RCON Console (optional)

Enable in `server.properties`:

```properties
enable-rcon=true
rcon.port=25575
rcon.password=YourPassword
```

Then fill in the parameters in the `/settings` interface.

## System Metrics

CPU/RAM resources are read from the host's `/proc` (bind-mount). Historical graphs are recorded every 5 minutes in SQLite.

## Update

```bash
git pull && docker compose up -d --build web
```

## Changelog

### v1.9.0
- **Feat**: browser push notifications — bell in the navbar, Web Push subscription (VAPID), join/leave notifications (Android, iOS 16.4+, desktop)

### v1.8.0
- **Feat**: PWA (Progressive Web App) — installable on mobile (Android/iOS), Minecraft pixel art icon, cache-free service worker (real-time data)

### v1.7.0
- **Feat**: Discord button on dashboard — official blurple SVG logo, configurable link in `/settings`, only shown when set

### v1.6.2
- **Fix**: playtime stats — ongoing session counted (join without leave)
- **Fix**: history purge resets `_live_players` → automatic re-log of connected players within 30s

### v1.6.1
- **UI**: logout button in navbar (visible only when logged in as admin)
- **UI**: `/settings` page in 2 columns (config left, maintenance right)

### v1.6.0
- **Feat**: Maintenance section in `/settings` — purge connection history (> 30d / 90d / all), purge chart metrics, SQLite VACUUM with DB size display

### v1.5.1
- **Fix**: machine uptime in System Resources — generic algorithm `CLOCK_BOOTTIME − starttime(PID 1)`, reliable on LXC Proxmox, KVM VM and bare-metal
- **Fix**: Network I/O and Disk I/O charts always flat — race condition between SSE stream (5s window) and recorder (5min window) on shared `_prev_*` globals; each caller now has its own state

### v1.5.0
- Extended system metrics: disk, network KB/s, disk I/O KB/s, VM uptime
- New 24h charts: CPU/RAM/Disk %, Network I/O, Disk I/O
- `SRV_PATH` configurable in `.env` for disk monitoring

### v1.4.0
- Dark / light theme persisted (localStorage) with nav toggle
- Server banner and favicon customizable from the UI (admin upload)
- Minecraft server uptime displayed in the status card (read from `latest.log` + SQLite)

### v1.3.0
- Statistics page: playtime per player, peak hours, historical charts (Chart.js)

### v1.2.0
- Player modal: UUID, skin type (Steve/Alex), cape — Mojang data proxied server-side
- Kick / Ban from the UI (admin, RCON)

### v1.1.0
- RCON command cheatsheet
- Replaced `mcrcon` with a native async RCON implementation (fix `signal only works in main thread`)
- App versioning (`web/VERSION` displayed in footer)

## Roadmap

- ~~Auto favicon from Minecraft server icon (status broadcast)~~
- ~~Ban-list management from the UI (RCON)~~
- ~~Multi-server support~~
- [x] PWA (Progressive Web App) — installable on mobile
- [x] Browser push notifications (player join/leave)

## Contributing

Contributions are welcome! To propose an improvement:

1. Fork the repository
2. Create a branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'feat: ...'`)
4. Push (`git push origin feature/my-feature`)
5. Open a Pull Request

For bugs, open an issue describing the reproduction steps.

## License

MIT — see [LICENSE](LICENSE).
