const socket = io({
    reconnectionAttempts: 5,
    timeout: 10000,
});

const state = {
    room: null,
    playerId: localStorage.getItem("liarGamePlayerId"),
    roomCode: localStorage.getItem("liarGameRoomCode"),
};

const $ = (selector) => document.querySelector(selector);

const screens = {
    home: $("#home-screen"),
    game: $("#game-screen"),
};

const views = {
    lobby: $("#lobby-view"),
    clue: $("#clue-view"),
    voting: $("#voting-view"),
    results: $("#results-view"),
};

function showToast(message) {
    const toast = $("#toast");
    toast.textContent = message;
    toast.classList.remove("hidden");
    window.clearTimeout(showToast.timeout);
    showToast.timeout = window.setTimeout(() => toast.classList.add("hidden"), 3200);
}

function playerName(playerId) {
    const player = state.room?.players.find((item) => item.id === playerId);
    return player ? player.name : "Unknown";
}

function currentPlayer() {
    return state.room?.players.find((player) => player.id === state.playerId);
}

function isHost() {
    return currentPlayer()?.isHost === true;
}

function showGameScreen() {
    screens.home.classList.add("hidden");
    screens.game.classList.remove("hidden");
}

function showPhase(phase) {
    Object.values(views).forEach((view) => view.classList.add("hidden"));
    if (views[phase]) {
        views[phase].classList.remove("hidden");
    }
}

function renderPlayers() {
    const list = $("#player-list");
    list.innerHTML = "";

    state.room.players.forEach((player) => {
        const row = document.createElement("li");
        row.className = "player-row";

        const name = document.createElement("span");
        name.className = "player-name";
        name.textContent = player.id === state.playerId ? `${player.name} (You)` : player.name;

        const tags = document.createElement("span");
        if (player.isHost) {
            tags.appendChild(makeTag("Host", "host"));
        }
        if (!player.connected) {
            tags.appendChild(makeTag("Offline", "offline"));
        }

        row.append(name, tags);
        list.appendChild(row);
    });

    $("#player-count").textContent = `${state.room.players.length}/${state.room.maxPlayers}`;
}

function makeTag(text, className = "") {
    const tag = document.createElement("span");
    tag.className = `tag ${className}`;
    tag.textContent = text;
    return tag;
}

function renderScoreboard() {
    const list = $("#scoreboard-list");
    list.innerHTML = "";

    [...state.room.players]
        .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name))
        .forEach((player) => {
            const row = document.createElement("li");
            row.className = "score-row";
            row.innerHTML = `<strong>${escapeHtml(player.name)}</strong><span>${player.score}</span>`;
            list.appendChild(row);
        });
}

function renderHeader() {
    $("#room-code-title").textContent = state.room.code;
    $("#round-label").textContent = state.room.phase === "lobby"
        ? "Lobby"
        : `Round ${state.room.roundNumber}`;
    $("#copy-code-button").textContent = "";
}

function renderStatus() {
    const status = $("#status-card");
    const player = currentPlayer();
    const hostName = playerName(state.room.hostId);

    if (state.room.phase === "lobby") {
        status.textContent = player?.isHost
            ? "You are the host. Start when at least three players have joined."
            : `${hostName} is hosting. Waiting for the game to start.`;
    } else if (state.room.phase === "clue") {
        status.textContent = state.room.currentTurnId === state.playerId
            ? "Your turn. Give one clue without making the word too obvious."
            : `${playerName(state.room.currentTurnId)} is giving a clue.`;
    } else if (state.room.phase === "voting") {
        status.textContent = player?.hasVoted
            ? "Vote locked. Waiting for the remaining players."
            : "All clues are in. Vote for the player you think is lying.";
    } else {
        status.textContent = "Round complete. Check the reveal and scores.";
    }
}

function renderLobby() {
    const count = state.room.players.filter((player) => player.connected).length;
    $("#lobby-message").textContent = `${count} connected player${count === 1 ? "" : "s"}. Minimum ${state.room.minPlayers} required.`;

    const startButton = $("#start-game-button");
    startButton.classList.toggle("hidden", !isHost());
    startButton.disabled = count < state.room.minPlayers;
}

function renderClues(selector = "#clue-list") {
    const list = $(selector);
    if (!list) {
        return;
    }

    list.innerHTML = "";

    state.room.players
        .filter((player) => player.clue)
        .forEach((player) => {
            const row = document.createElement("li");
            row.className = "clue-row";
            row.innerHTML = `<strong>${escapeHtml(player.name)}</strong><span class="clue-text">${escapeHtml(player.clue)}</span>`;
            list.appendChild(row);
        });

    if (!list.children.length) {
        const empty = document.createElement("li");
        empty.className = "clue-row";
        empty.textContent = "No clues yet.";
        list.appendChild(empty);
    }
}

function renderCluePhase() {
    $("#secret-word").textContent = state.room.personalWord || "Waiting...";
    $("#turn-message").textContent = state.room.currentTurnId === state.playerId
        ? "It is your turn."
        : `Waiting for ${playerName(state.room.currentTurnId)}.`;
    $("#clue-form").classList.toggle("hidden", state.room.currentTurnId !== state.playerId);
    $("#clue-input").value = "";
    renderClues();
}

function renderVoting() {
    const wrapper = $("#vote-options");
    const me = currentPlayer();
    wrapper.innerHTML = "";

    state.room.players
        .filter((player) => player.connected)
        .forEach((player) => {
            const button = document.createElement("button");
            button.className = "vote-card";
            button.disabled = player.id === state.playerId || me?.hasVoted;
            button.innerHTML = `<strong>${escapeHtml(player.name)}</strong><span>${player.id === state.playerId ? "You" : "Suspect"}</span>`;
            button.addEventListener("click", () => socket.emit("submit_vote", { accusedId: player.id }));
            wrapper.appendChild(button);
        });
}

function renderResults() {
    const results = state.room.results;
    if (!results) {
        return;
    }

    const liar = playerName(results.liarId);
    const outcome = results.caughtLiar
        ? "The group caught the Liar. Non-liars gained 1 point."
        : "The Liar survived. The Liar gained 3 points.";

    $("#results-summary").innerHTML = `
        <p><strong>Liar:</strong> ${escapeHtml(liar)}</p>
        <p><strong>Secret word:</strong> ${escapeHtml(results.secretWord)}</p>
        <p>${escapeHtml(outcome)}</p>
    `;

    const maxVotes = Math.max(1, ...Object.values(results.voteCounts));
    const voteResults = $("#vote-results");
    voteResults.innerHTML = "";

    Object.entries(results.voteCounts).forEach(([playerId, count]) => {
        const row = document.createElement("div");
        row.className = "vote-bar";
        const width = Math.round((count / maxVotes) * 100);
        row.innerHTML = `
            <strong>${escapeHtml(playerName(playerId))}</strong>
            <span class="bar-track"><span class="bar-fill" style="width:${width}%"></span></span>
            <span>${count}</span>
        `;
        voteResults.appendChild(row);
    });

    $("#play-again-button").classList.toggle("hidden", !isHost());
}

function renderRoom() {
    showGameScreen();
    renderHeader();
    renderPlayers();
    renderScoreboard();
    renderStatus();
    showPhase(state.room.phase);

    if (state.room.phase === "lobby") {
        renderLobby();
    } else if (state.room.phase === "clue") {
        renderCluePhase();
    } else if (state.room.phase === "voting") {
        renderVoting();
        renderClues("#voting-clue-list");
    } else if (state.room.phase === "results") {
        renderResults();
    }
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function getName() {
    return $("#player-name").value.trim() || "Player";
}

$("#create-room-button").addEventListener("click", () => {
    if (!socket.connected) {
        showToast("Still connecting to the game server. Try again in a moment.");
        return;
    }
    socket.emit("create_room", { name: getName() });
});

$("#join-room-button").addEventListener("click", () => {
    if (!socket.connected) {
        showToast("Still connecting to the game server. Try again in a moment.");
        return;
    }

    const roomCode = $("#room-code").value.trim().toUpperCase();
    if (!roomCode) {
        showToast("Enter a room code.");
        return;
    }
    socket.emit("join_room", {
        roomCode,
        name: getName(),
        playerId: state.playerId,
    });
});

$("#start-game-button").addEventListener("click", () => {
    socket.emit("start_game");
});

$("#submit-clue-button").addEventListener("click", () => {
    const clueInput = $("#clue-input");
    socket.emit("submit_clue", { clue: clueInput.value });
});

$("#clue-input").addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        $("#submit-clue-button").click();
    }
});

$("#play-again-button").addEventListener("click", () => {
    socket.emit("play_again");
});

$("#copy-code-button").addEventListener("click", async () => {
    if (!state.room?.code) {
        return;
    }
    try {
        await navigator.clipboard.writeText(state.room.code);
        showToast("Room code copied.");
    } catch {
        showToast(state.room.code);
    }
});

socket.on("room_joined", ({ roomCode, playerId }) => {
    state.roomCode = roomCode;
    state.playerId = playerId;
    localStorage.setItem("liarGameRoomCode", roomCode);
    localStorage.setItem("liarGamePlayerId", playerId);
});

socket.on("room_state", (room) => {
    state.room = room;
    renderRoom();
});

socket.on("error_message", ({ message }) => {
    showToast(message);
});

socket.on("connect", () => {
    showToast("Connected to the game server.");
    if (state.roomCode && state.playerId) {
        socket.emit("join_room", {
            roomCode: state.roomCode,
            name: getName(),
            playerId: state.playerId,
        });
    }
});

socket.on("connect_error", () => {
    showToast("Cannot connect to the game server. Check the Render logs.");
});

socket.on("disconnect", () => {
    showToast("Disconnected from the game server. Reconnecting...");
});
