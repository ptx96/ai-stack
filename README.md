# Unsloth Studio + Hermes Agent

Docker Compose stack: Unsloth Studio (ROCm) serves the models, Hermes Agent uses Studio's OpenAI-compatible API.

Studio loads one model at a time. Switch models from the Studio UI.

## Prerequisites

- Docker with Compose v2
- AMD GPU (`/dev/kfd`, `/dev/dri`) and an SSH public key (optional, for container SSH)

## Setup

1. Create the env file and the local folders:

   ```bash
   cp .env.example .env
   mkdir -p workspace hermes-data
   cp config.example.yaml hermes-data/config.yaml
   ```

2. Fill in the host values and secrets:

   ```bash
   sed -i "s/^VIDEO_GID=.*/VIDEO_GID=$(getent group video | cut -d: -f3)/" .env
   sed -i "s/^RENDER_GID=.*/RENDER_GID=$(getent group render | cut -d: -f3)/" .env
   sed -i "s/^PUID=.*/PUID=$(id -u)/; s/^PGID=.*/PGID=$(id -g)/" .env
   sed -i "s|^SSH_KEY=.*|SSH_KEY=\"$(cat ~/.ssh/id_ed25519.pub)\"|" .env
   sed -i "s/^HERMES_DASHBOARD_SECRET=.*/HERMES_DASHBOARD_SECRET=$(openssl rand -hex 32)/" .env
   sed -i "s/^API_SERVER_KEY=.*/API_SERVER_KEY=$(openssl rand -hex 32)/" .env
   ```

   Then set `UNSLOTH_STUDIO_PASSWORD`, `JUPYTER_PASSWORD` and `HERMES_DASHBOARD_PASSWORD` in `.env`.

## Start

1. Start Studio:

   ```bash
   docker compose up -d unsloth-studio
   ```

2. Open http://localhost:8000, sign in as `unsloth`, and load a model (**Select model**).
3. Create an API key under **Settings > API** and put it in `.env` as `UNSLOTH_API_KEY`. It is shown only once.
4. Set `model.default` in `hermes-data/config.yaml` to the id returned by:

   ```bash
   set -a; source .env; set +a
   curl -H "Authorization: Bearer $UNSLOTH_API_KEY" http://localhost:8000/v1/models
   ```

5. Start everything:

   ```bash
   docker compose up -d
   ```

## Access

| Service | URL |
|---|---|
| Unsloth Studio | http://localhost:8000 |
| JupyterLab | http://localhost:8888 |
| SSH | `ssh -p 2222 root@localhost` |
| Hermes dashboard | http://localhost:9119 |
| Hermes webapp | http://localhost:9120 |
| Hermes API | http://localhost:8642/v1 |

Ports are bound to `127.0.0.1`. Set `UNSLOTH_BIND=0.0.0.0` in `.env` to expose Studio, Jupyter and SSH on the LAN, and `HERMES_BIND=0.0.0.0` for the Hermes API and dashboards.

## Verify

```bash
docker compose ps
docker compose exec hermes sh -c 'curl -s -H "Authorization: Bearer $UNSLOTH_API_KEY" http://unsloth:8000/v1/models'
```

Hermes must run its own tools. If tool calls never execute, Studio's server-side tools are intercepting them and need to be off (`--disable-tools`).

## Change the model

Load another model in Studio, then in Hermes run `/model custom`, or update `model.default` in `hermes-data/config.yaml` and run `docker compose restart hermes`.

## Configure Hermes

Edit `hermes-data/config.yaml` (and `hermes-data/.env` for provider keys or messaging tokens), then:

```bash
docker compose restart hermes
```

## Telegram

1. Create a bot with [@BotFather](https://t.me/BotFather) and note the token. Get your numeric user ID from [@userinfobot](https://t.me/userinfobot).
2. Add these values to the project `.env` file next to `docker-compose.yml` (replace the example values):

   ```bash
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   TELEGRAM_ALLOWED_USERS=123456789
   ```

3. Recreate Hermes so Compose passes the updated environment into the container: `docker compose up -d --force-recreate hermes`.

`TELEGRAM_ALLOWED_USERS` is required: without it the gateway denies every user. Hermes uses polling, so no inbound port is needed.

## Update

Set `HERMES_IMAGE_TAG` in `.env` for Hermes, then:

```bash
docker compose pull
docker compose up -d
```

## Stop and logs

```bash
docker compose logs -f
docker compose down
```

Models, Studio data and Hermes data live in `~/.cache/huggingface`, the `unsloth-studio` volume and `hermes-data/`, so `down` does not delete them.
