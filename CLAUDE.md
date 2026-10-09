# Project rules

## About this project

Tour de Bytur is a drinking board game with a night-out theme, inspired by property board games. It runs locally on a Mac: one shared host screen shows the board, and everyone plays from their phone on the same wifi by scanning a QR code. It is built with Python, Flask and Flask-SocketIO. The game text is in Danish; code and comments are in English.

- `app.py` holds the Flask routes and Socket.IO events. The server owns the game state and sends the full state to every screen after each change.
- `game/state.py` holds the rules as plain Python with no Flask, so they can be tested directly.
- `data/board.json` and `data/settings.json` hold the bars, groups and numbers, so the game can be adapted without touching code.
- `templates/` and `static/` hold the host screen (`/`) and the phone page (`/play`).

## Commands

- Install: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
- Run: `.venv/bin/python app.py`, then open http://localhost:5001 (port 5000 is taken by AirPlay on macOS)
- Test: `.venv/bin/pytest`

## Git workflow

- Never commit or push directly to `main`.
- Before starting a new change, switch to `main` and pull the latest changes.
- Create a new branch for each change, named like `feature/short-description` or `fix/short-description`.
- Write short, clear commit messages that say what changed and why.
- When a change is finished, commit it and push the branch right away. Don't wait for me to ask.
- After pushing, open a pull request with `gh pr create` and give me the link.
- If a pull request is already open for this branch, just push the new commits to it instead of opening a new one.
- Never merge pull requests yourself. I review and merge them on GitHub.

## Security

- This repository is public. Anyone can read everything in it.
- Before every commit, check the changes for passwords, API keys, tokens or other secrets. If you find any, stop and tell me.
- Never commit `.env` files. Make sure `.env` is listed in `.gitignore`.
