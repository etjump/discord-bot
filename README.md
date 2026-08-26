# ETJump discord bot

Discord bot for ETJump/Trickjump Discord.

## Commands

Commands are defined in `config/commands.json` (falling back to the committed `commands.json`),
so adding a simple command just requires editing the file on the server.

Default commands:

| Command  | Reply                     |
| -------- | ------------------------- |
| `/hello` | `Hello!`                  |
| `/ping`  | `Pong!`                   |
| `/help`  | `Help text placeholder.`  |
| `/info`  | `Info placeholder.`       |

### Built-in commands

* `/reload` re-reads the commands config and re-syncs commands with Discord without restarting.
* `/setstatus` changes the bot's status message at runtime (`/setstatus text:Beep boop type:watching`, or `text:-` to clear).

## Bot status

The status shown under the bot's name defaults to a custom status **"Beep
boop"**. Configure it in `.env` (changes apply on restart):

```
BOT_ACTIVITY=Beep boop            # status text; empty = no status
BOT_ACTIVITY_TYPE=custom          # custom | watching | playing | listening | competing | streaming
```

`/setstatus` overrides it at runtime (until the next restart).

## Adding a simple command

1. Edit the live command config and add an entry:
   ```json
   {
     "name": "rules",
     "description": "Show the server rules.",
     "response": "1. Don't be a dick."
   }
   ```
2. Restart to register it with Discord:
   ```
   docker compose restart
   ```
   (Or use `/reload` in Discord — no restart needed.)

Config commands are limited to a static `response`.
Anything needing logic — arguments, embeds, dynamic content etc — goes in code (see Structure below).

## Layout

When deployed, the file layout is as follows:

| Path | Purpose |
| ---- | ------- |
| `/opt/etjump-discord-bot` | build source (git checkout) |
| `/etc/etjump-discord-bot` | `.env` + `docker-compose.yml` |
| `/var/lib/etjump-discord-bot/config` | live command definitions (`commands.json`) |

The docker-compose paths default to this - you may override them via `BOT_SRC` / `BOT_ETC` / `BOT_DATA` (used automatically by `deploy.sh`).

## Run locally

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # set TOKEN
mkdir -p config && cp commands.json config/commands.json
python bot.py
```

## Deploy

Requires git and Docker 24+ (with the compose plugin). `deploy.sh` installs Docker if missing,
clones the repo to `/opt/etjump-discord-bot`, installs the compose file and `.env` into `/etc/etjump-discord-bot`,
and seeds runtime data into `/var/lib/etjump-discord-bot`. Run it as root / with sudo.

Fresh install:

```
sudo apt install -y git                       # if needed
sudo git clone git@github.com:etjump/discord-bot.git /opt/etjump-discord-bot
sudo bash /opt/etjump-discord-bot/deploy.sh
```

On the first run it stops after creating `/etc/etjump-discord-bot/.env` — set `TOKEN` in it,
then run it again to seed the command config, build and start.

Update / redeploy:

```
sudo bash /opt/etjump-discord-bot/deploy.sh
```

This pulls the latest code, rebuilds the image and restarts the container.
The container has `restart: unless-stopped`, so it comes back up on server reboots.
`.env` (in `/etc`) and the config data (in `/var/lib`) are never committed and survive updates.

## Structure

- `bot.py` — entrypoint; registers config commands, defines `/reload`
- `config.py` — reads environment variables; resolves the commands file path
- `dynamic_commands.py` — loads the commands config and registers/reloads commands
- `commands.json` — committed default command definitions (template)
- `docker-compose.yml` — service definition with the standard layout paths

Future features that need logic should be added as modules loaded from `bot.py`
(py-cord cogs when you have many commands); settings go in `config.py` and `.env`.
