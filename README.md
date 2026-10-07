# ProjectBacklog

**Stop scrolling your Steam library. Tell it how much time you have tonight, and it tells you what to play.**

ProjectBacklog is a local command-line tool that reads your Steam library, lets you label each game with where you really are in it, and then recommends what to play next based on those labels, your recent playtime, and how long you've been away from each game. It exists to help you *finish* what you've started instead of buying and starting more.

> **Status:** early release (v0.1). Command-line only, runs entirely on your own machine.

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Features](#features)
- [Quick start](#quick-start)
- [Usage](#usage)
- [Command reference](#command-reference)
- [How recommendations work](#how-recommendations-work)
- [Configuration](#configuration)
- [Your data and privacy](#your-data-and-privacy)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Design choices](#design-choices)
- [Roadmap](#roadmap)
- [Development](#development)
- [License and disclaimer](#license-and-disclaimer)

---

## Why this exists

Steam knows how many hours you've put into a game, but it can't tell you whether you finished it, abandoned it, or are halfway through and just got busy. Most "what should I play?" tools either pick randomly or guess from genres and review scores.

ProjectBacklog takes a different approach:

- **You tell it the truth about each game** (playing, not started, finished, dropped, or endless). It never guesses whether you finished something.
- **It scores the games you're actually in the middle of**, favoring ones you were playing recently and penalizing ones you've been away from long enough that you'd need to re-learn the controls and the plot.
- **It takes tonight's time into account.** With 45 minutes free, a game you left months ago is a worse pick than it would be on a free weekend.
- **Every recommendation comes with reasons**, so you can see why a game ranked where it did and disagree with it.

## Features

- Pulls your library, playtime, and last-played dates from the Steam Web API.
- Stores everything in a local SQLite database. Re-syncing is safe to repeat and never overwrites your labels.
- Games that disappear from your library (refunds, removals) are kept and marked, not deleted.
- Fast interactive labeling: one keypress per game, saved immediately.
- `pick` command with a time budget (`--minutes 90`) and plain-English reasons for each suggestion.
- A "still playing this?" check for games you marked as playing but haven't launched in over a year.
- Everything runs locally. No account, no server, no telemetry.

## Quick start

### Requirements

- **Python 3.10 or newer** (check with `python --version`)
- A **Steam account** whose game details are public (see step 3)
- A free **Steam Web API key**

### 1. Get a Steam Web API key

Go to <https://steamcommunity.com/dev/apikey>, sign in, and register a key. The form asks for a domain name; `localhost` is fine for personal use. Treat the key like a password and don't share or commit it.

### 2. Find your SteamID64

ProjectBacklog needs your **17-digit SteamID64** (it looks like `7656119XXXXXXXXXX`), not your profile name.

- If your profile URL looks like `steamcommunity.com/profiles/7656119...`, that number is your SteamID64.
- If your URL uses a custom name (`steamcommunity.com/id/yourname`), look it up with a SteamID finder such as <https://steamid.io>.

### 3. Make your game details public

The Steam API can only read your library if it's public.

In Steam: **Profile → Edit Profile → Privacy Settings → Game details → Public.** If there is an option to keep your total playtime private, turn it off, since playtime is what the scoring relies on.

### 4. Install

```bash
git clone https://github.com/<your-username>/ProjectBacklog.git
cd ProjectBacklog

python -m venv venv
```

Activate the virtual environment:

```bash
# Windows (Command Prompt or PowerShell)
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Then install the project:

```bash
pip install -e .
```

### 5. Configure

Copy the example settings file and fill in your values:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Edit `.env`:

```
STEAM_API_KEY=your_key_here
STEAM_ID=your_id_here
```

`.env` is listed in `.gitignore` and must never be committed.

### 6. First run

Run these from inside the project folder (so the `.env` file is found):

```bash
python -m projectbacklog sync     # fetch your library
python -m projectbacklog label    # tell it where you are in each game
python -m projectbacklog pick --minutes 90
```

That's the whole workflow: **sync, label, pick.**

## Usage

### Sync your library

```bash
python -m projectbacklog sync
```

The first run saves everything. Later runs refresh playtime and report what changed (new games, games that came back, games that left). Run it whenever you like; it's safe to repeat.

### Label your games

```bash
python -m projectbacklog label
```

This walks through your most-played unlabeled games, one at a time:

```
Keys: f=finished  p=playing  d=dropped  e=endless  n=not started  s or Enter=skip  q=quit

[1/30] Example RPG  (41.7h, last played 2026-10-04)  >
```

Press one key per game. Every answer is saved immediately, so you can quit with `q` at any time and continue later. Games you've never launched are skipped by default (pass `--include-unplayed` to include them).

To set or fix a single game's label directly:

```bash
python -m projectbacklog status "elden ring" finished
python -m projectbacklog status 1245620 dropped          # by Steam app id
python -m projectbacklog status "elden ring" clear       # remove the label
```

A partial name works. If several games match, the command lists them with their app ids and asks you to be more specific.

### Pick what to play

```bash
python -m projectbacklog pick --minutes 90
```

```
Tonight (90 min): your top 3

1. Example RPG   (score 64.0)
     - You marked it Playing
     - Last played 3 days ago
     - 5.0h in the last 2 weeks, so you're warmed up
     - 42h invested

2. Fresh Purchase   (score 20.0)
     - Marked Not started: a fresh start, nothing to re-learn

3. Sample Adventure   (score 17.8)
     - You marked it Playing
     - Cold: last played 6 months ago, expect some re-learning
     - 30h invested
     - Short session (90 min): getting back into a game you left a while ago costs more

1 played game(s) are unlabeled and weren't considered. Run:  python -m projectbacklog label
```

Try different time budgets to see how the order changes: a long evening makes a game you left a while ago more attractive, and a short one favors whatever you were playing recently. Leave `--minutes` off to see picks with no time limit.

If you have games marked *playing* that you haven't launched in over a year, `pick` will ask about them first (see [The "still playing?" check](#the-still-playing-check)).

### Browse your library

```bash
python -m projectbacklog list --limit 0
```

```
last played   playtime  status       name
2026-10-02      150.0h  endless      Endless Sandbox
2026-10-04       41.7h  playing      Example RPG
2026-03-21       30.0h  playing      Sample Adventure
2026-09-07       15.0h  finished     Beaten Classic
2026-09-27       10.0h  -            Unlabeled Game
never             0.0h  not started  Fresh Purchase
```

Useful variations:

```bash
python -m projectbacklog list --sort recent --limit 10
python -m projectbacklog list --status unlabeled        # what still needs a label
python -m projectbacklog list --status finished
python -m projectbacklog list --include-removed         # games that left your library
```

`list`, `label`, `status`, and `pick` work offline and don't need your API key. Only `sync` talks to Steam.

## Command reference

| Command | What it does |
|---|---|
| `sync` | Fetches your Steam library into the local database. Safe to repeat. |
| `label [--limit N] [--include-unplayed]` | Interactively labels your most-played unlabeled games (default 30; `0` = all). |
| `status GAME VALUE` | Sets one game's label. `GAME` is an app id or part of a name. `VALUE` is `playing`, `not_started`, `finished`, `dropped`, `endless`, or `clear`. |
| `pick [--minutes N] [--top N] [--no-prompt]` | Recommends what to play. `--minutes` is your time budget (default: no limit), `--top` how many to show (default 3), `--no-prompt` turns off the stale-label questions. |
| `list [--sort S] [--limit N] [--status S] [--include-removed]` | Shows stored games. `--sort` is `playtime` (default), `recent`, or `name`. `--limit 0` shows all. |

Status values are forgiving: `not_started`, `not-started`, and `"not started"` all work.

## How recommendations work

### Only games you labeled are recommended

| Label | Meaning | Recommended? |
|---|---|---|
| `playing` | You're in the middle of it | Yes, scored on recent play, hours, and time away |
| `not_started` | You own it but haven't begun | Yes, flat "fresh start" score |
| `finished` | You beat it | No |
| `dropped` | You gave up on it | No |
| `endless` | No ending to finish (multiplayer, sandbox, roguelike) | No |
| *(unlabeled)* | You haven't said | No, but `pick` tells you how many are waiting |

### The score for a game you're playing

Starting from a base value, the score adjusts for:

- **Momentum:** hours played in the last two weeks add points (up to a cap), because you're warmed up and getting back in is easy.
- **Investment:** total hours add a modest bonus on a logarithmic curve, so 200 hours isn't ten times more meaningful than 20.
- **Time away:** a penalty that grows the longer it's been since you last played, because re-learning controls, builds, and plot gets harder. Half the maximum penalty applies after about 90 days.
- **Tonight's time:** the time-away penalty gets heavier for short sessions and lighter for long ones. A game you played yesterday isn't affected by session length at all.

A game marked `not_started` gets a flat score, so an active game beats a fresh purchase unless the active game has gone cold. A game you abandoned years ago while still labeled `playing` loses to a fresh start.

### Tuning the numbers

All the constants live in one place, the `Weights` dataclass at the top of `src/projectbacklog/scoring.py`:

| Setting | Default | Meaning |
|---|---|---|
| `playing_bonus` | 35 | Base value of a game marked playing |
| `not_started_base` | 20 | Value of a game marked not started |
| `momentum_per_hour` | 4 | Points per hour played in the last two weeks |
| `momentum_cap` | 20 | Maximum momentum bonus |
| `investment_scale` | 6 | Points = scale × log10(1 + hours played) |
| `cold_half_life_days` | 90 | Days until half of the time-away penalty applies |
| `cold_max_penalty` | 25 | Penalty for a game left untouched indefinitely |
| `reference_session_minutes` | 120 | What counts as a "normal" evening |
| `time_factor_min` / `time_factor_max` | 0.5 / 2.0 | How much session length can scale the time-away penalty |

These are educated first guesses, not science. If the picks feel wrong after a week of use, edit them and run the tests.

### The "still playing?" check

A game marked *playing* that you haven't launched in over a year is probably one you quietly gave up on. Rather than guess, `pick` asks:

- It only asks about games last launched more than a year ago **and** whose label hasn't been set or confirmed in the past year.
- `y` keeps the label and resets the one-year clock. `n` marks the game dropped. `s` or Enter decides later (you'll be asked again). `q` stops asking.
- It only prompts in an interactive terminal. With `--no-prompt`, or when input is piped, it prints a one-line warning instead.

### How sync treats your data

- Steam's data (name, playtime, last played) lives in one table and is refreshed on every sync.
- **Your data** (labels) lives in a separate table that sync never touches.
- A game that disappears from your library is marked as removed, hidden from `list` unless you ask, and restored automatically if it comes back. Your label on it is kept.
- If Steam ever returns an empty library, sync refuses to apply it rather than marking everything as removed.
- Each sync is a single transaction: it either fully applies or leaves the database unchanged.

## Configuration

Settings come from a `.env` file in the project folder or from ordinary environment variables.

| Variable | Required | Meaning |
|---|---|---|
| `STEAM_API_KEY` | For `sync` | Your Steam Web API key |
| `STEAM_ID` | For `sync` | Your 17-digit SteamID64 |
| `DB_PATH` | No | Where to store the database. Default: `data/projectbacklog.db` next to `.env`. |

The tool looks for `.env` starting in the current folder and walking upward, so run commands from inside the project folder.

## Your data and privacy

- Everything is stored locally in one SQLite file (by default `data/projectbacklog.db`). Back it up if you care about your labels.
- ProjectBacklog has no server and sends no telemetry. Its only network traffic is the request to Steam's API during `sync`.
- That request includes your API key, as Steam's API requires. Error messages from the tool never print your key.
- `.env` and `data/` are gitignored. Before you push your own fork or changes, run `git status` and confirm neither appears. If a key is ever committed by accident, regenerate it on Steam's API key page, since deleting the file later doesn't remove it from git history.

## Troubleshooting

**"Steam returned no games."**
Almost always a privacy setting. Set **Game details** to **Public** (see [Quick start](#3-make-your-game-details-public)) and confirm `STEAM_ID` is correct. It can take a moment for a privacy change to take effect.

**"Steam rejected the request. Check STEAM_API_KEY in .env."**
The key is wrong, revoked, or has stray spaces or quotes around it. Copy it again from <https://steamcommunity.com/dev/apikey>.

**"STEAM_ID must be your 17-digit SteamID64."**
You used a profile name or a shortened number. Use the 17-digit ID (see [Quick start](#2-find-your-steamid64)).

**"Missing STEAM_API_KEY" even though you created `.env`.**
On Windows, file extensions are often hidden, so the file may really be called `.env.txt`. Turn on "File name extensions" in File Explorer and rename it. Also make sure you're running commands from inside the project folder.

**`No module named projectbacklog`.**
Activate your virtual environment and run `pip install -e .` from the project folder.

**PowerShell won't activate the virtual environment.**
Use Command Prompt instead, or allow local scripts for your user with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

**`No games stored yet. Run: python -m projectbacklog sync`**
You haven't synced yet, or `DB_PATH` points somewhere different from where you synced.

**A game is missing from `list`.**
Only games your account owns are included, so Family Sharing games don't appear. A game that left your library is hidden unless you pass `--include-removed`.

**Playtime looks wrong.**
The numbers are Steam's own totals. Offline play and a few other cases can make them differ from what you remember.

**Strange characters in game names on Windows.**
Some older consoles can't display every symbol. The tool replaces unprintable characters instead of crashing; Windows Terminal displays them properly.

## Limitations

- **Steam only.** Games from other launchers, and games that never touched Steam, aren't included.
- **Owned games only.** Family Sharing libraries aren't supported. Steam's family library data isn't available through the normal API key, and support could be added later as an opt-in feature.
- **No game-length data.** The tool doesn't know whether a game takes 8 hours or 80, so "hours invested" is a loose proxy for how far in you are.
- **Labels are manual on purpose.** See [Design choices](#design-choices).
- **Command line only** for now.

## Design choices

**Why doesn't it guess which games you've finished?**
Steam has no "finished" flag. Achievements are a poor proxy, since plenty of people beat a game with a fraction of them unlocked. A wrong guess means a wrong recommendation, so the tool asks you once and remembers.

**Why are unlabeled games never recommended?**
The recommender only works from facts you confirmed. Rather than risk suggesting a game you already beat, it leaves unlabeled games out and reminds you how many are waiting.

**Why store your labels separately from Steam's data?**
Steam's numbers change on every sync. Your labels shouldn't. Keeping them in separate tables means a sync can never overwrite something you told the tool.

**Why is the scoring a separate, pure module?**
`scoring.py` does no database or network access. It takes plain facts in and returns a score with reasons, which makes it easy to test thoroughly and easy to tune.

## Roadmap

Ideas for future versions, not promises:

- **Smarter completion estimates** using achievement data (for example, the rarest achievement you've unlocked as a sign of how far in you are), checked against your own labels before it influences any recommendation.
- **Demo mode** with sample data, so anyone can try the tool without a Steam key.
- **Optional Family Sharing support**, strictly opt-in.
- **Session tracking** to record real play sessions, not just Steam's totals.
- **Quit notes** so you can leave yourself a one-line reminder of where you stopped.

## Development

Set up a development environment:

```bash
pip install -e ".[dev]"
python -m pytest
```

Project layout:

```
ProjectBacklog/
├── pyproject.toml
├── README.md
├── LICENSE
├── .env.example
├── .gitignore
├── src/projectbacklog/
│   ├── __main__.py    # enables `python -m projectbacklog`
│   ├── cli.py         # commands and output formatting
│   ├── config.py      # loads .env and settings
│   ├── steam.py       # Steam Web API client (network only)
│   ├── db.py          # SQLite schema and queries
│   ├── sync.py        # Steam data -> database, safely repeatable
│   ├── labels.py      # your labels and the interactive labeling session
│   ├── scoring.py     # pure scoring functions and Weights
│   ├── picker.py      # stale-label detection and confirmation prompts
│   └── fmt.py         # small display helpers
└── tests/
    ├── test_sync.py
    ├── test_labels.py
    ├── test_scoring.py
    └── test_picker.py
```

Guidelines for contributions:

- Keep network code in `steam.py` and scoring code free of I/O.
- Changes to scoring behavior should come with tests; the existing tests document the intended behavior.
- Never commit `.env`, your database, or your virtual environment.

Issues and pull requests are welcome.

## License and disclaimer

Released under the MIT License. See [LICENSE](LICENSE).

ProjectBacklog is an independent project. It is not affiliated with, endorsed by, or sponsored by Valve Corporation. Steam is a trademark of Valve Corporation. Use of the Steam Web API is subject to Valve's terms.