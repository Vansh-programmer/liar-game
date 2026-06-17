# Liar Game

A complete real-time multiplayer web game built with Flask, Flask-SocketIO, HTML, CSS, and vanilla JavaScript.

## Folder Structure

```text
.
+-- app.py
+-- .gitignore
+-- requirements.txt
+-- README.md
+-- render.yaml
+-- templates/
|   +-- index.html
+-- static/
    +-- css/
    |   +-- styles.css
    +-- js/
        +-- app.js
+-- tests/
    +-- smoke_game_flow.py
```

## Install and Run Locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open `http://localhost:5000` in your browser.

## Test

After installing dependencies, run:

```bash
python tests/smoke_game_flow.py
```

The smoke test verifies the homepage and a full three-player Socket.IO flow: create room, join room, start round, submit clues, vote, reveal, and score.

## Render Deployment

1. Push this project to GitHub.
2. In Render, create a new Web Service from the repository.
3. Use these settings:
   - Runtime: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --worker-class eventlet -w 1 app:app`
4. Add an environment variable named `PYTHON_VERSION` with a value such as `3.11.9`.
5. Deploy the service and open the Render URL.

Socket.IO uses long-lived connections, so the start command uses an Eventlet worker. The game stores rooms in process memory, which is fine for one Render instance. For multiple instances or persistent rooms, move room state into Redis or a database.

## How the Game Logic Works

- A player creates a room and becomes the host.
- Other players join with the five-character room code.
- Room state is stored in memory in the `rooms` dictionary in `app.py`.
- The host starts the round once at least three connected players are present.
- The server picks one random word from the built-in word list and one random connected player as the Liar.
- Normal players receive the secret word. The Liar receives only `You are the Liar`.
- The server shuffles turn order and accepts one clue per active player.
- After all clues are submitted, the room moves to voting.
- Each connected player votes for another connected player.
- When all eligible votes are in, the server counts votes and reveals the result.
- If one player has the most votes and that player is the Liar, every non-liar gets 1 point.
- Otherwise the Liar survives and gets 3 points.
- The host can click Play again to return the room to the lobby while keeping players and scores.

## Socket Events

- `create_room`: creates a room for a player name.
- `join_room`: joins or reconnects to a room.
- `start_game`: host-only event to begin a round.
- `submit_clue`: submits the current player's clue.
- `submit_vote`: submits a vote during the voting phase.
- `play_again`: host-only event to reset for another round.
- `leave_room`: marks the current player disconnected.
- `room_state`: server broadcast containing the current room state.
- `error_message`: server response for invalid actions.
