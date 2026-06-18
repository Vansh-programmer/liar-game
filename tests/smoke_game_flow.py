import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import app, socketio


def latest_state(client):
    messages = client.get_received()
    room_states = [message for message in messages if message["name"] == "room_state"]
    assert room_states, f"No room_state event received. Messages: {messages}"
    return room_states[-1]["args"][0]


def main():
    flask_client = app.test_client()
    response = flask_client.get("/")
    assert response.status_code == 200
    assert b"Liar Game" in response.data

    clients = [
        socketio.test_client(app, flask_test_client=app.test_client()),
        socketio.test_client(app, flask_test_client=app.test_client()),
        socketio.test_client(app, flask_test_client=app.test_client()),
    ]

    clients[0].emit("create_room", {"name": "Host"})
    joined_messages = clients[0].get_received()
    room_joined = next(message for message in joined_messages if message["name"] == "room_joined")
    room_code = room_joined["args"][0]["roomCode"]

    clients[1].emit("join_room", {"roomCode": room_code, "name": "Alice"})
    clients[2].emit("join_room", {"roomCode": room_code, "name": "Bob"})

    for client in clients:
        client.get_received()

    clients[0].emit("start_game")
    states = [latest_state(client) for client in clients]
    assert states[0]["phase"] == "clue"
    assert len(states[0]["players"]) == 3
    assert states[0]["roundNumber"] == 1

    clue_count = 0
    while states[0]["phase"] == "clue":
        current_turn_id = states[0]["currentTurnId"]
        current_client_index = next(
            index for index, state in enumerate(states) if state["viewerId"] == current_turn_id
        )
        clients[current_client_index].emit("submit_clue", {"clue": f"clue {clue_count + 1}"})
        states = [latest_state(client) for client in clients]
        clue_count += 1

    assert clue_count == 3
    assert states[0]["phase"] == "voting"
    assert all(player["clue"] for player in states[0]["players"] if player["connected"])

    for index, client in enumerate(clients):
        state = states[index]
        voter_id = state["viewerId"]
        target_id = next(
            player["id"]
            for player in state["players"]
            if player["id"] != voter_id and player["connected"]
        )
        client.emit("submit_vote", {"accusedId": target_id})
        received_states = []
        for socket_client in clients:
            messages = socket_client.get_received()
            room_states = [message for message in messages if message["name"] == "room_state"]
            if room_states:
                received_states.append(room_states[-1]["args"][0])
        if received_states:
            states = received_states

    final_state = states[0]
    assert final_state["phase"] == "results"
    assert final_state["results"]["liarId"]
    assert final_state["results"]["secretWord"]
    assert sum(final_state["results"]["voteCounts"].values()) == 3

    print("Smoke test passed: create, join, start, clues, voting, reveal, scoring.")


if __name__ == "__main__":
    main()
