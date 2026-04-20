# Minecraft WebUI — Specs

## Contexte

Refonte complète et unification des deux services existants sur la VM `minecraft.home.lan` :
- `/srv/minecraft/players/` → service systemd `players.service` (notifieur Discord)
- `/srv/minecraft/status/` → service systemd `webstatus.service` (web UI Flask obsolète)

Les deux services systemd seront stoppés/désactivés une fois le nouveau container opérationnel.

---

## Infos serveur Minecraft

| Paramètre        | Valeur                                    |
|------------------|-------------------------------------------|
| Host             | `minecraft.home.lan`                      |
| Port Java        | `25565`                                   |
| Query activé     | oui (`enable-query=true`)                 |
| Logs             | `/srv/minecraft/server/logs/latest.log`   |
| Serveur Java     | à jour (dernière version)                 |

---

## Stack cible (Docker)

Docker à installer sur la VM avant déploiement.

```
minecraft_webui/
├── docker-compose.yml
├── .env                        ← secrets (webhook URL, mot de passe admin)
├── .env.example
├── Caddyfile                   ← reverse proxy HTTPS
├── web/                        ← service FastAPI unifié
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── minecraft.py
│   ├── system.py
│   ├── auth.py
│   ├── settings_store.py       ← persistance config webhook (JSON sur volume)
│   ├── templates/
│   └── static/
└── discord-notifier/           ← service notifieur async
    ├── Dockerfile
    ├── requirements.txt
    └── main.py
```

### Services Docker Compose

| Service             | Rôle                                                  |
|---------------------|-------------------------------------------------------|
| `web`               | FastAPI — dashboard, joueurs, journaux, config UI     |
| `discord-notifier`  | Polling mcstatus + envoi webhook Discord              |
| `caddy`             | Reverse proxy HTTPS avec cert wildcard `*.home.lan`   |

---

## Web UI

- **Framework** : FastAPI + Jinja2 côté serveur
- **Design** : Material Design 3 (Material Web Components via CDN) + thème Minecraft
- **Pages** :
  - `/` — Dashboard (statut serveur, métriques système CPU/RAM/Swap, joueurs en ligne)
  - `/players` — Liste des joueurs avec skin (mc-heads.net)
  - `/logs` — 100 dernières lignes du log serveur (auto-refresh 10s)
  - `/settings` — Config webhook Discord (protégée par mot de passe)

### Métriques système

- psutil avec mount `/proc` host → `HOST_PROC=/host/proc`
- CPU, RAM (used/total Go + %), Swap (used/total Go + %)

---

## Discord

- **1 webhook** (join + leave dans le même canal)
- URL configurable depuis `/settings` (sauvegardée dans un fichier JSON sur volume Docker)
- Délai de polling configurable depuis `/settings`
- Embeds colorés : vert (connexion) / rouge (déconnexion) + avatar skin

---

## Authentification `/settings`

- Mot de passe unique défini dans `.env` → `ADMIN_PASSWORD=...`
- Session cookie signé (via `itsdangerous` ou `starlette`)
- Pas de gestion multi-utilisateurs

---

## Réseau & HTTPS

| Paramètre          | Valeur                              |
|--------------------|-------------------------------------|
| FQDN               | `minecraft.home.lan`                |
| Accès              | LAN uniquement                      |
| Reverse proxy      | Caddy                               |
| Certificat         | Wildcard `*.home.lan` (déjà existant) |
| Port exposé Caddy  | `443`                               |
| Port interne web   | `8000`                              |

### Caddyfile (sketch)

```
minecraft.home.lan {
    tls /certs/home.lan.crt /certs/home.lan.key
    reverse_proxy web:8000
}
```

Le certificat wildcard sera monté en volume dans le container Caddy.

---

## Migration

1. Installer Docker + Docker Compose sur `minecraft.home.lan`
2. Copier le repo + créer `.env` depuis `.env.example`
3. `docker compose up -d`
4. Vérifier que tout fonctionne
5. `systemctl stop players webstatus && systemctl disable players webstatus`

---

## Variables d'environnement (.env)

```env
MC_HOST=minecraft.home.lan
MC_PORT=25565
MC_LOG_PATH=/srv/minecraft/server/logs/latest.log
ADMIN_PASSWORD=changeme
# Webhook et délai configurables depuis l'UI — stockés dans /data/settings.json
```
