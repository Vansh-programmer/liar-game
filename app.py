import os
import random
import string
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO, emit, join_room, leave_room


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")


MIN_PLAYERS = 3
MAX_PLAYERS = 12
ROOM_CODE_LENGTH = 5

WORDS = [
    "Airport", "Anchor", "Backpack", "Bakery", "Balloon", "Banana", "Beach",
    "Bicycle", "Blanket", "Bridge", "Camera", "Candle", "Castle", "Chocolate",
    "Cinema", "Clock", "Coffee", "Compass", "Computer", "Concert", "Cookie",
    "Crown", "Desert", "Diamond", "Dinosaur", "Doctor", "Dragon", "Elevator",
    "Farmer", "Feather", "Festival", "Fireworks", "Forest", "Galaxy", "Garden",
    "Guitar", "Hamburger", "Harbor", "Helicopter", "Hospital", "Iceberg",
    "Island", "Jacket", "Jungle", "Keyboard", "Kingdom", "Lantern", "Library",
    "Lighthouse", "Mailbox", "Market", "Mermaid", "Microscope", "Moonlight",
    "Mountain", "Museum", "Notebook", "Ocean", "Octopus", "Orchestra", "Painter",
    "Pancake", "Parachute", "Penguin", "Piano", "Pirate", "Pizza", "Planet",
    "Popcorn", "Postcard", "Puzzle", "Rainbow", "Restaurant", "Robot", "Rocket",
    "Sailboat", "Sandwich", "Satellite", "School", "Scissors", "Shampoo",
    "Skateboard", "Snowman", "Spaceship", "Stadium", "Submarine", "Sunflower",
    "Supermarket", "Telescope", "Theater", "Thunder", "Toothbrush", "Treasure",
    "Umbrella", "Unicorn", "Vacation", "Volcano", "Wallet", "Waterfall",
    "Window", "Wizard", "Zoo", "Campfire", "Carnival", "Cucumber", "Domino",
    "Espresso", "Fireplace", "Glacier", "Honeycomb", "Kangaroo", "Marathon",
    "Necklace", "Observatory", "Passport", "Quicksand", "Raindrop", "Suitcase",
    "Teacup", "Violin", "Windmill", "Xylophone", "Yogurt", "Zeppelin",
]


@dataclass
class Player:
    id: str
    name: str
    sid: str
    score: int = 0
    is_host: bool = False
    connected: bool = True
    clue: Optional[str] = None
    vote_for: Optional[str] = None


@dataclass
class Room:
    code: str
    players: Dict[str, Player] = field(default_factory=dict)
    phase: str = "lobby"
    round_number: int = 0
    secret_word: Optional[str] = None
    liar_id: Optional[str] = None
    turn_order: List[str] = field(default_factory=list)
    current_turn_index: int = 0
    votes: Dict[str, str] = field(default_factory=dict)
    last_results: Optional[dict] = None

    def connected_players(self) -> List[Player]:
        return [player for player in self.players.values() if player.connected]

    def active_player_ids(self) -> List[str]:
        return [player_id for player_id, player in self.players.items() if player.connected]

    def host(self) -> Optional[Player]:
        for player in self.players.values():
            if player.is_host:
                return player
        return None


rooms: Dict[str, Room] = {}
player_room_by_sid: Dict[str, str] = {}
player_id_by_sid: Dict[str, str] = {}


def make_room_code() -> str:
    while True:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=ROOM_CODE_LENGTH))
        if code not in rooms:
            return code


def clean_name(name: str) -> str:
    name = (name or "").strip()
    return name[:24] if name else "Player"


def public_player(player: Player) -> dict:
    return {
        "id": player.id,
        "name": player.name,
        "score": player.score,
        "isHost": player.is_host,
        "connected": player.connected,
        "clue": player.clue,
        "hasVoted": player.vote_for is not None,
    }


def room_payload(room: Room, viewer_id: Optional[str] = None) -> dict:
    current_turn_id = None
    if room.phase == "clue" and room.turn_order and room.current_turn_index < len(room.turn_order):
        current_turn_id = room.turn_order[room.current_turn_index]

    personal_role = None
    personal_word = None
    if room.phase in {"clue", "voting", "results"} and viewer_id in room.players:
        if viewer_id == room.liar_id:
            personal_role = "liar"
            personal_word = "You are the Liar"
        else:
            personal_role = "normal"
            personal_word = room.secret_word

    return {
        "code": room.code,
        "phase": room.phase,
        "roundNumber": room.round_number,
        "players": [public_player(player) for player in room.players.values()],
        "minPlayers": MIN_PLAYERS,
        "maxPlayers": MAX_PLAYERS,
        "currentTurnId": current_turn_id,
        "turnOrder": room.turn_order,
        "votes": room.votes if room.phase == "results" else {},
        "results": room.last_results if room.phase == "results" else None,
        "personalRole": personal_role,
        "personalWord": personal_word,
        "viewerId": viewer_id,
        "hostId": room.host().id if room.host() else None,
    }


def emit_room_state(room: Room) -> None:
    for player in room.players.values():
        socketio.emit("room_state", room_payload(room, player.id), room=player.sid)


def emit_error(message: str) -> None:
    emit("error_message", {"message": message})


def get_room_and_player() -> tuple[Optional[Room], Optional[Player]]:
    room_code = player_room_by_sid.get(request.sid)
    player_id = player_id_by_sid.get(request.sid)
    room = rooms.get(room_code) if room_code else None
    player = room.players.get(player_id) if room and player_id else None
    return room, player


def assign_new_host(room: Room) -> None:
    if room.host() and room.host().connected:
        return

    for player in room.players.values():
        player.is_host = False

    connected_players = room.connected_players()
    if connected_players:
        connected_players[0].is_host = True


def reset_round_fields(room: Room) -> None:
    for player in room.players.values():
        player.clue = None
        player.vote_for = None
    room.secret_word = None
    room.liar_id = None
    room.turn_order = []
    room.current_turn_index = 0
    room.votes = {}
    room.last_results = None


def advance_to_next_connected_turn(room: Room) -> None:
    room.current_turn_index += 1
    while room.current_turn_index < len(room.turn_order):
        next_player = room.players.get(room.turn_order[room.current_turn_index])
        if next_player and next_player.connected:
            return
        room.current_turn_index += 1
    room.phase = "voting"


def finish_round(room: Room) -> None:
    vote_counts: Dict[str, int] = {player_id: 0 for player_id in room.players}
    for accused_id in room.votes.values():
        if accused_id in vote_counts:
            vote_counts[accused_id] += 1

    highest_votes = max(vote_counts.values()) if vote_counts else 0
    top_accused = [player_id for player_id, count in vote_counts.items() if count == highest_votes]
    caught_liar = room.liar_id in top_accused and len(top_accused) == 1

    if caught_liar:
        for player_id, player in room.players.items():
            if player_id != room.liar_id:
                player.score += 1
    elif room.liar_id in room.players:
        room.players[room.liar_id].score += 3

    room.last_results = {
        "liarId": room.liar_id,
        "secretWord": room.secret_word,
        "caughtLiar": caught_liar,
        "voteCounts": vote_counts,
        "topAccused": top_accused,
    }
    room.phase = "results"


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True, "rooms": len(rooms)})


@socketio.on("connect")
def handle_connect():
    app.logger.info("Socket connected: %s", request.sid)


@socketio.on("create_room")
def create_room(data):
    name = clean_name(data.get("name"))
    room_code = make_room_code()
    player_id = str(uuid.uuid4())
    player = Player(id=player_id, name=name, sid=request.sid, is_host=True)
    room = Room(code=room_code, players={player_id: player})
    rooms[room_code] = room
    player_room_by_sid[request.sid] = room_code
    player_id_by_sid[request.sid] = player_id
    join_room(room_code)
    app.logger.info("Room %s created by %s (%s)", room_code, name, request.sid)
    emit("room_joined", {"roomCode": room_code, "playerId": player_id})
    emit_room_state(room)


@socketio.on("join_room")
def join_existing_room(data):
    room_code = (data.get("roomCode") or "").strip().upper()
    name = clean_name(data.get("name"))
    requested_player_id = data.get("playerId")
    room = rooms.get(room_code)

    if not room:
        emit_error("Room not found.")
        return

    existing_player = room.players.get(requested_player_id) if requested_player_id else None
    if existing_player:
        existing_player.sid = request.sid
        existing_player.name = name or existing_player.name
        existing_player.connected = True
        player_id = existing_player.id
    else:
        if room.phase != "lobby":
            emit_error("This game has already started.")
            return
        if len(room.players) >= MAX_PLAYERS:
            emit_error("This room is full.")
            return
        player_id = str(uuid.uuid4())
        room.players[player_id] = Player(id=player_id, name=name, sid=request.sid)

    player_room_by_sid[request.sid] = room_code
    player_id_by_sid[request.sid] = player_id
    join_room(room_code)
    assign_new_host(room)
    emit("room_joined", {"roomCode": room_code, "playerId": player_id})
    emit_room_state(room)


@socketio.on("start_game")
def start_game():
    room, player = get_room_and_player()
    if not room or not player:
        emit_error("You are not in a room.")
        return
    if not player.is_host:
        emit_error("Only the host can start the game.")
        return
    if room.phase != "lobby":
        emit_error("The game has already started.")
        return

    connected_player_ids = room.active_player_ids()
    if len(connected_player_ids) < MIN_PLAYERS:
        emit_error(f"At least {MIN_PLAYERS} players are required.")
        return

    reset_round_fields(room)
    room.phase = "clue"
    room.round_number += 1
    room.secret_word = random.choice(WORDS)
    room.liar_id = random.choice(connected_player_ids)
    room.turn_order = connected_player_ids[:]
    random.shuffle(room.turn_order)
    room.current_turn_index = 0
    emit_room_state(room)


@socketio.on("submit_clue")
def submit_clue(data):
    room, player = get_room_and_player()
    clue = (data.get("clue") or "").strip()

    if not room or not player:
        emit_error("You are not in a room.")
        return
    if room.phase != "clue":
        emit_error("It is not clue time.")
        return
    if not room.turn_order or room.turn_order[room.current_turn_index] != player.id:
        emit_error("It is not your turn.")
        return
    if not clue:
        emit_error("Enter a clue first.")
        return

    player.clue = clue[:80]
    advance_to_next_connected_turn(room)

    emit_room_state(room)


@socketio.on("submit_vote")
def submit_vote(data):
    room, player = get_room_and_player()
    accused_id = data.get("accusedId")

    if not room or not player:
        emit_error("You are not in a room.")
        return
    if room.phase != "voting":
        emit_error("It is not voting time.")
        return
    if accused_id not in room.players:
        emit_error("Choose a valid player.")
        return
    if accused_id == player.id:
        emit_error("You cannot vote for yourself.")
        return
    if not room.players[accused_id].connected:
        emit_error("You cannot vote for a disconnected player.")
        return

    player.vote_for = accused_id
    room.votes[player.id] = accused_id

    eligible_voters = set(room.active_player_ids())
    if eligible_voters and eligible_voters.issubset(set(room.votes.keys())):
        finish_round(room)

    emit_room_state(room)


@socketio.on("play_again")
def play_again():
    room, player = get_room_and_player()
    if not room or not player:
        emit_error("You are not in a room.")
        return
    if not player.is_host:
        emit_error("Only the host can start another round.")
        return
    if room.phase != "results":
        emit_error("Finish the current round first.")
        return

    room.phase = "lobby"
    reset_round_fields(room)
    emit_room_state(room)


@socketio.on("leave_room")
def leave_current_room():
    room, player = get_room_and_player()
    if not room or not player:
        return

    leave_room(room.code)
    player.connected = False
    player_room_by_sid.pop(request.sid, None)
    player_id_by_sid.pop(request.sid, None)
    assign_new_host(room)

    if (
        room.phase == "clue"
        and room.turn_order
        and room.current_turn_index < len(room.turn_order)
        and player.id == room.turn_order[room.current_turn_index]
    ):
        advance_to_next_connected_turn(room)

    emit_room_state(room)


@socketio.on("disconnect")
def handle_disconnect():
    room_code = player_room_by_sid.pop(request.sid, None)
    player_id = player_id_by_sid.pop(request.sid, None)
    room = rooms.get(room_code) if room_code else None
    player = room.players.get(player_id) if room and player_id else None

    if not room or not player:
        return

    player.connected = False
    app.logger.info("Socket disconnected: %s", request.sid)
    assign_new_host(room)

    if room.phase == "clue" and room.turn_order and room.current_turn_index < len(room.turn_order):
        if player.id == room.turn_order[room.current_turn_index]:
            advance_to_next_connected_turn(room)

    if room.phase == "voting":
        active_voters = set(room.active_player_ids())
        room.votes = {voter_id: accused_id for voter_id, accused_id in room.votes.items() if voter_id in active_voters}
        if len(active_voters) <= 1 or (active_voters and active_voters.issubset(set(room.votes.keys()))):
            finish_round(room)

    emit_room_state(room)


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
