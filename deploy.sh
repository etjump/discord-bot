#!/usr/bin/env bash
#
# deploy.sh — idempotent deploy script for the ETJump discord bot.
# Handles both a fresh install on a new VPS and updating an existing one.
#
# Layout (same convention as the other discord bots):
#   /opt/etjump-discord-bot/     build source (git checkout)
#   /etc/etjump-discord-bot/     .env + docker-compose.yml
#   /var/lib/etjump-discord-bot/ runtime data (config/commands.json)
#
# Usage (run as root / with sudo):
#   Fresh install:  sudo bash /opt/etjump-discord-bot/deploy.sh
#   Update:         sudo bash /opt/etjump-discord-bot/deploy.sh
#
# On a fresh install the script stops after creating .env so you can set your
# token, then you simply run it again. The container name, compose file and
# data directory are fixed; override the dirs with APP_DIR/ETC_DIR/DATA_DIR
# env vars if you need a different layout.

set -euo pipefail

# ---- configuration ----------------------------------------------------------

REPO_URL="${REPO_URL:-git@github.com:etjump/discord-bot.git}"
APP_DIR="${APP_DIR:-/opt/etjump-discord-bot}"
ETC_DIR="${ETC_DIR:-/etc/etjump-discord-bot}"
DATA_DIR="${DATA_DIR:-/var/lib/etjump-discord-bot}"

# ---- helpers ----------------------------------------------------------------

say() { printf '\033[1;36m[deploy]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[deploy]\033[0m %s\n' "$*" >&2; exit 1; }
need_cmd() { command -v "$1" >/dev/null 2>&1; }

install_docker() {
  if ! need_cmd docker || ! docker compose version >/dev/null 2>&1; then
    say "Installing docker + compose plugin..."
    if need_cmd apt-get; then
      apt-get update
      apt-get install -y docker.io docker-compose-plugin
    else
      die "Unsupported distro — install Docker and the compose plugin manually, then re-run."
    fi
  fi
}

# ---- steps -----------------------------------------------------------------

need_cmd git || die "git is required (apt-get install -y git)"

install_docker

# Make sure the daemon is running.
if ! docker info >/dev/null 2>&1; then
  if need_cmd systemctl; then
    systemctl enable --now docker
  else
    die "Docker daemon is not running — start it and re-run."
  fi
fi

# 1. Get the source into APP_DIR.
if [ -d "$APP_DIR/.git" ]; then
  say "Updating existing checkout in $APP_DIR..."
  git -C "$APP_DIR" pull --ff-only
else
  say "Cloning $REPO_URL into $APP_DIR..."
  git clone "$REPO_URL" "$APP_DIR"
fi

# 2. Install the compose file and .env into ETC_DIR.
mkdir -p "$ETC_DIR"
cp "$APP_DIR/docker-compose.yml" "$ETC_DIR/docker-compose.yml"

if [ ! -f "$ETC_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$ETC_DIR/.env"
  say "Created $ETC_DIR/.env from .env.example."
  say "Set TOKEN in $ETC_DIR/.env, then run this script again to start the bot."
  exit 0
fi

# 3. Seed runtime data into DATA_DIR. config/ is gitignored, so edits there
#    survive git pulls and don't need commits.
mkdir -p "$DATA_DIR/config"
if [ ! -f "$DATA_DIR/config/commands.json" ]; then
  cp "$APP_DIR/commands.json" "$DATA_DIR/config/commands.json"
  say "Created $DATA_DIR/config/commands.json from the repo default."
  say "Edit it to add/change simple commands, then run: docker compose restart"
fi

# 4. Warn about keys added to .env.example that are missing from .env.
missing_keys="$(comm -23 \
  <(grep -E '^[A-Z_]+=' "$APP_DIR/.env.example" | cut -d= -f1 | sort) \
  <(grep -E '^[A-Z_]+=' "$ETC_DIR/.env" | cut -d= -f1 | sort))"
if [ -n "$missing_keys" ]; then
  printf '\033[1;33m[deploy]\033[0m .env is missing keys from .env.example:\n'
  printf '  %s\n' $missing_keys
  printf '  Add them to %s, then run this script again.\n' "$ETC_DIR/.env"
fi

# 5. Build and start. Pass the layout into compose via BOT_* vars.
export BOT_SRC="$APP_DIR" BOT_ETC="$ETC_DIR" BOT_DATA="$DATA_DIR"
cd "$ETC_DIR"

say "Building and starting container (compose in $ETC_DIR)..."
docker compose up -d --build

say "Done. Status:"
docker compose ps
printf '\n\033[1;36m[deploy]\033[0m Recent logs:\n'
docker compose logs --tail=20