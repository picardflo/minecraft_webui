# Minecraft WebUI

Dashboard de monitoring pour serveur Minecraft Java Edition, avec notifications Discord et console RCON.

![Version](https://img.shields.io/badge/version-1.2.0-green)
![Docker](https://img.shields.io/badge/docker-compose-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)

## Fonctionnalités

- **Dashboard** — statut serveur, latence, joueurs en ligne, uptime, ressources système (CPU/RAM/Swap) en temps réel via SSE
- **Joueurs** — liste des connectés avec skins Minecraft ; clic sur un joueur → modal UUID, type de skin, cape ; **Kick / Ban** admin (RCON)
- **Historique** — journal des connexions/déconnexions persisté en SQLite (filtres 24h / 7j / 30j)
- **Statistiques** — temps de jeu par joueur, heures de pointe, historique CPU/RAM 24h (Chart.js)
- **Journaux** — 100 dernières lignes du log serveur avec coloration par niveau et filtre en temps réel
- **Notifications Discord** — embed avec skin du joueur envoyé à chaque connexion/déconnexion
- **Console RCON** — terminal interactif avec mémo des commandes courantes (admin)
- **Config UI** — webhook Discord et paramètres RCON modifiables depuis l'interface, protégés par mot de passe

## Stack

| Service | Rôle |
|---|---|
| `web` | FastAPI + Jinja2 + Uvicorn |
| `discord-notifier` | Polling async + webhooks Discord |
| `caddy` | Reverse proxy HTTPS |

## Prérequis

- Docker + Docker Compose
- Serveur Minecraft Java avec `enable-status=true` dans `server.properties`

## Installation

```bash
git clone https://github.com/your-username/minecraft_webui.git
cd minecraft_webui

cp .env.example .env
nano .env

docker compose up -d --build
```

## Configuration (.env)

```env
MC_HOST=your.minecraft.server.com   # Adresse du serveur Minecraft
MC_PORT=25565                        # Port Java (défaut 25565)
MC_LOG_PATH=/srv/minecraft/server/logs/latest.log

ADMIN_PASSWORD=changeme              # Mot de passe pour /settings et /console
SECRET_KEY=change-this-to-a-long-random-string

DOMAIN=localhost                     # Domaine utilisé par Caddy
```

## SSL / TLS

Trois modes disponibles, sélectionnés via `CADDYFILE` dans `.env` :

### Mode 1 — Self-signed (défaut, LAN/local)

Aucune configuration supplémentaire. Caddy génère un certificat local automatiquement.

```env
DOMAIN=mc.home.lan
# CADDYFILE non défini → utilise Caddyfile (tls internal)
```

> Le navigateur affichera un avertissement de sécurité la première fois.

### Mode 2 — Let's Encrypt (domaine public)

Ports 80 et 443 doivent être ouverts et le domaine doit pointer vers votre IP.

```env
DOMAIN=mc.example.com
CADDYFILE=Caddyfile.letsencrypt
TLS_EMAIL=admin@example.com
```

### Mode 3 — Certificat existant (wildcard, entreprise…)

Déposer `fullchain.pem` et `privkey.pem` dans le dossier `./certs/`.

```env
DOMAIN=mc.home.lan
CADDYFILE=Caddyfile.custom
```

## Console RCON (optionnel)

Activer dans `server.properties` :

```properties
enable-rcon=true
rcon.port=25575
rcon.password=VotreMotDePasse
```

Puis renseigner les paramètres dans l'interface `/settings`.

## Métriques système

Les ressources CPU/RAM sont lues depuis `/proc` de la machine hôte (bind-mount). Les graphiques historiques sont enregistrés toutes les 5 minutes en SQLite.

## Mise à jour

```bash
git pull && docker compose up -d --build web
```

## Migration depuis des services systemd

Une fois la stack Docker opérationnelle :

```bash
systemctl stop players webstatus
systemctl disable players webstatus
```
