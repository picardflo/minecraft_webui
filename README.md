# Minecraft WebUI

Dashboard de monitoring pour serveur Minecraft Java, avec notifications Discord et console RCON.

## Fonctionnalités

- **Dashboard** — statut serveur, latence, joueurs en ligne, ressources système (CPU/RAM/Swap) en temps réel via SSE
- **Joueurs** — liste des connectés avec skins Minecraft, mise à jour automatique ; clic sur un joueur → modal avec UUID, type de skin, cape ; boutons **Kick / Ban** pour les admins (RCON)
- **Historique** — journal des connexions/déconnexions persisté en SQLite (filtres 24h / 7j / 30j)
- **Journaux** — 100 dernières lignes du log serveur avec coloration par niveau
- **Notifications Discord** — embed avec skin du joueur envoyé à chaque connexion/déconnexion
- **Console RCON** — terminal interactif avec mémo des commandes courantes (admin)
- **Config UI** — webhook Discord et paramètres RCON modifiables depuis l'interface, protégés par mot de passe
- **Versioning** — version affichée dans le footer (fichier `web/VERSION`)

## Stack

| Service | Rôle |
|---|---|
| `web` | FastAPI + Jinja2 + Uvicorn |
| `discord-notifier` | Polling async + webhooks Discord |
| `caddy` | Reverse proxy HTTPS (cert wildcard) |

## Prérequis

- Docker + Docker Compose installés sur la VM
- Certificat wildcard `*.home.lan` disponible sur l'hôte
- Serveur Minecraft Java avec `enable-status=true` dans `server.properties`

## Installation

```bash
# Cloner le repo
cd /srv
git clone ssh://git@gogs.home.lan:2222/fpicard/minecraft_webui.git
cd minecraft_webui

# Configurer l'environnement
cp .env.example .env
nano .env

# Démarrer
docker compose up -d --build
```

## Configuration (.env)

```env
MC_HOST=minecraft.home.lan       # Adresse du serveur Minecraft
MC_PORT=25565                    # Port Java
MC_LOG_PATH=/srv/minecraft/server/logs/latest.log

ADMIN_PASSWORD=changeme          # Mot de passe pour /settings et /console
SECRET_KEY=change-this-secret    # Clé de signature des cookies

CERT_DIR=/etc/ssl/home.lan       # Dossier contenant fullchain.pem + privkey.pem
```

Le webhook Discord et les paramètres RCON sont configurables directement depuis `/settings`.

## Console RCON (optionnel)

Activer dans `/srv/minecraft/server/server.properties` :

```properties
enable-rcon=true
rcon.port=25575
rcon.password=VotreMotDePasse
```

Puis renseigner les paramètres dans l'interface `/settings`.

## Mise à jour

```bash
cd /srv/minecraft_webui && git pull && docker compose up -d --build web
```

## Migration depuis les anciens services

Une fois la stack Docker opérationnelle :

```bash
systemctl stop players webstatus
systemctl disable players webstatus
```
