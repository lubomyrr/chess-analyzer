const state = {
    games: [],
    currentView: "dashboard",
    currentGame: null,
    currentMoves: [],
    currentStats: null,
    reviewIndex: -1,
    pollTimer: null,
    uploadMode: "link",
};

const statusLabels = {
    queued: "Queued",
    analyzing: "Analyzing",
    completed: "Completed",
    failed: "Failed",
};

const engineLabels = {
    stockfish: "Stockfish",
};

const pageCopy = {
    dashboard: ["Private workspace", "Overview"],
    games: ["Activity", "Matches"],
};

const pieceImageCodes = {
    K: "wk", Q: "wq", R: "wr", B: "wb", N: "wn", P: "wp",
    k: "bk", q: "bq", r: "br", b: "bb", n: "bn", p: "bp",
};

const pieceImageBaseUrl = "/static/assets/pieces";

document.addEventListener("DOMContentLoaded", () => {
    bindNavigation();
    bindUpload();
    bindGames();
    document.querySelector(".brand").addEventListener("click", () => switchView("dashboard"));
    document.querySelector("#refresh-button").addEventListener("click", refreshData);
    const initialView = window.location.hash.slice(1);
    if (pageCopy[initialView]) switchView(initialView);
    window.addEventListener("hashchange", () => {
        const requestedView = window.location.hash.slice(1);
        if (pageCopy[requestedView] && requestedView !== state.currentView) switchView(requestedView);
    });
    refreshData();
});

function bindNavigation() {
    document.querySelectorAll("[data-view-target]").forEach((button) => {
        button.addEventListener("click", () => switchView(button.dataset.viewTarget));
    });

}

function bindUpload() {
    const form = document.querySelector("#upload-form");
    const input = document.querySelector("#pgn-file");
    const dropZone = document.querySelector("#drop-zone");

    document.querySelectorAll("[data-upload-mode]").forEach((button) => {
        button.addEventListener("click", () => setUploadMode(button.dataset.uploadMode));
    });

    input.addEventListener("change", () => updateFileLabel(input.files[0]));

    ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.add("dragging");
        });
    });

    ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
            event.preventDefault();
            dropZone.classList.remove("dragging");
        });
    });

    dropZone.addEventListener("drop", (event) => {
        const file = event.dataTransfer.files[0];
        if (!file) return;
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.files = transfer.files;
        updateFileLabel(file);
    });

    form.addEventListener("submit", uploadGame);
}

function setUploadMode(mode) {
    state.uploadMode = mode;
    document.querySelectorAll("[data-upload-mode]").forEach((button) => {
        button.classList.toggle("active", button.dataset.uploadMode === mode);
    });
    document.querySelector("#link-zone").classList.toggle("hidden", mode !== "link");
    document.querySelector("#drop-zone").classList.toggle("hidden", mode !== "file");
    document.querySelector("#paste-zone").classList.toggle("hidden", mode !== "text");
}

function bindGames() {
    document.querySelector("#close-analysis-button").addEventListener("click", closeAnalysis);
    document.querySelector("#reanalyze-button").addEventListener("click", reanalyzeCurrentGame);

    document.querySelector("#review-first").addEventListener("click", () => setReviewPosition(-1));
    document.querySelector("#review-previous").addEventListener("click", () => setReviewPosition(state.reviewIndex - 1));
    document.querySelector("#review-next").addEventListener("click", () => setReviewPosition(state.reviewIndex + 1));
    document.querySelector("#review-last").addEventListener("click", () => setReviewPosition(state.currentMoves.length - 1));
    document.querySelector("#review-moves").addEventListener("click", (event) => {
        const moveButton = event.target.closest("[data-review-index]");
        if (moveButton) setReviewPosition(Number(moveButton.dataset.reviewIndex));
    });

    document.addEventListener("keydown", (event) => {
        const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
        const panelIsOpen = !document.querySelector("#analysis-panel").classList.contains("hidden");
        if (isTyping || state.currentView !== "games" || !panelIsOpen) return;
        if (event.key === "ArrowLeft") setReviewPosition(state.reviewIndex - 1);
        if (event.key === "ArrowRight") setReviewPosition(state.reviewIndex + 1);
    });

    document.querySelectorAll("#recent-games, #matches-games").forEach((list) => {
        list.addEventListener("click", handleGameAction);
        list.addEventListener("keydown", (event) => {
        const row = event.target.closest(".game-row");
        if (row && event.target === row && ["Enter", " "].includes(event.key)) {
            event.preventDefault();
            openAnalysis(Number(row.dataset.gameId));
        }
        });
    });
}

async function refreshData() {
    const button = document.querySelector("#refresh-button");
    button.disabled = true;
    button.textContent = "Refreshing…";
    await Promise.allSettled([checkHealth(), loadGames()]);
    button.disabled = false;
    button.textContent = "Refresh";
}

async function checkHealth() {
    const dot = document.querySelector("#system-state-dot");
    const title = document.querySelector("#system-state-title");
    const copy = document.querySelector("#system-state-copy");
    try {
        const health = await request("/health/ready");
        dot.classList.add("online");
        title.textContent = "Services online";
        copy.textContent = health.database === "connected" ? "API and database connected" : "FastAPI online";
    } catch (error) {
        dot.classList.remove("online");
        title.textContent = "Connection unavailable";
        copy.textContent = "Check Docker containers";
    }
}

async function loadGames() {
    try {
        state.games = await request("/games");
        renderRecentGames();
    } catch (error) {
        renderMessage("#recent-games", error.message, "empty-state");
        renderMessage("#matches-games", error.message, "empty-state");
    }
}

function renderRecentGames() {
    const empty = '<div class="empty-state">Your first uploaded game will appear here.</div>';
    const recentContent = state.games.length
        ? state.games.slice(0, 4).map(gameRow).join("")
        : empty;
    const matchesContent = state.games.length
        ? state.games.map(gameRow).join("")
        : empty;
    document.querySelector("#recent-games").innerHTML = recentContent;
    document.querySelector("#matches-games").innerHTML = matchesContent;
}

function gameRow(game) {
    const symbol = game.user_color === "white" ? "♙" : "♟";
    const status = statusLabels[game.status] || game.status;
    const canAnalyze = !["queued", "analyzing"].includes(game.status);
    return `
        <div class="game-row" role="button" tabindex="0" data-game-action="open" data-game-id="${game.id}" title="Open analysis">
            <div class="game-players">
                <span class="game-color" title="Your color">${symbol}</span>
                <span>
                    <strong>${playerName(game.white_player, game.white_elo)} — ${playerName(game.black_player, game.black_elo)}</strong>
                    <small>Game ${game.id} · ${escapeHtml(engineLabels[game.engine] || game.engine)} · played as ${escapeHtml(game.user_color)}</small>
                </span>
            </div>
            <strong class="game-result">${escapeHtml(game.result)}</strong>
            <span class="status-badge status-${escapeHtml(game.status)}">${escapeHtml(status)}</span>
            <span class="game-date">${formatDate(game.played_at || game.created_at)}</span>
            <div class="row-actions">
                ${canAnalyze ? `<button class="row-button" type="button" data-game-action="analyze" data-game-id="${game.id}">Run</button>` : ""}
                <button class="row-button delete-button" type="button" data-game-action="delete" data-game-id="${game.id}">Delete</button>
            </div>
        </div>`;
}

async function handleGameAction(event) {
    const button = event.target.closest("[data-game-action]");
    if (!button) return;
    const gameId = Number(button.dataset.gameId);
    if (button.dataset.gameAction === "open") await openAnalysis(gameId);
    if (button.dataset.gameAction === "analyze") await queueAnalysis(gameId);
    if (button.dataset.gameAction === "delete") await deleteGame(gameId);
}

async function deleteGame(gameId) {
    if (!window.confirm("Delete this game and its analysis?")) return;
    try {
        await request(`/games/${gameId}`, { method: "DELETE" });
        if (state.currentGame?.id === gameId) closeAnalysis();
        await loadGames();
        showNotice("Game deleted.");
    } catch (error) {
        showNotice(error.message, true);
    }
}

async function openAnalysis(gameId, quiet = false) {
    if (!quiet) switchView("games");
    const panel = document.querySelector("#analysis-panel");
    document.querySelector(".games-recent-panel").classList.add("hidden");
    panel.classList.remove("hidden");
    setText("#analysis-title", "Loading analysis…");
    setText("#analysis-meta", "");
    renderMessage("#review-moves", "Loading Stockfish moves…", "loading-state");

    try {
        const [game, analysis] = await Promise.all([
            request(`/games/${gameId}`),
            request(`/games/${gameId}/analysis`),
        ]);
        const isSameGame = state.currentGame?.id === game.id;
        state.currentGame = game;
        state.currentMoves = analysis.moves;
        state.currentStats = {
            white: analysis.white_stats,
            black: analysis.black_stats,
        };
        if (!isSameGame || state.reviewIndex >= state.currentMoves.length) state.reviewIndex = -1;
        renderAnalysis();
        if (!quiet) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        manageAnalysisPolling(game);
    } catch (error) {
        setText("#analysis-title", "Could not open this game");
        setText("#analysis-meta", error.message);
        renderMessage("#review-moves", error.message, "empty-state");
    }
}

function renderAnalysis() {
    const game = state.currentGame;
    if (!game) return;
    document.querySelector("#reanalyze-button").disabled = ["queued", "analyzing"].includes(game.status);
    setText("#analysis-title", `${game.white_player} — ${game.black_player}`);
    setText(
        "#analysis-meta",
        `${game.result} · ${engineLabels[game.engine] || game.engine} · ${statusLabels[game.status] || game.status} · ${formatDate(game.played_at || game.created_at)}`
    );

    renderPlayerStatistics();
    renderMoveLedger();
    setReviewPosition(state.reviewIndex);
}

function renderPlayerStatistics() {
    if (!state.currentGame) {
        document.querySelector("#top-player").innerHTML = "";
        document.querySelector("#bottom-player").innerHTML = "";
        return;
    }

    const bottomColor = state.currentGame?.user_color || "white";
    const topColor = bottomColor === "white" ? "black" : "white";
    document.querySelector("#top-player").innerHTML = playerBoardLabel(
        topColor,
        state.currentStats?.[topColor],
        "Opponent"
    );
    document.querySelector("#bottom-player").innerHTML = playerBoardLabel(
        bottomColor,
        state.currentStats?.[bottomColor],
        "You"
    );
}

function playerBoardLabel(color, stats, role) {
    const game = state.currentGame;
    const name = color === "white" ? game.white_player : game.black_player;
    const elo = color === "white" ? game.white_elo : game.black_elo;
    const accuracy = stats?.accuracy == null ? "—" : `${stats.accuracy}%`;
    return `
        <div class="board-player-identity">
            <div><strong>${playerName(name, elo)}</strong><small>${role} · ${escapeHtml(color)}</small></div>
        </div>
        <div class="board-player-stats" title="Accuracy is calculated from centipawn loss">
            <span><b>${accuracy}</b> Accuracy</span>
            <span><b>${stats?.inaccuracies ?? 0}</b> Inaccuracies</span>
            <span><b>${stats?.mistakes ?? 0}</b> Mistakes</span>
            <span><b>${stats?.blunders ?? 0}</b> Blunders</span>
        </div>`;
}

function renderMoveLedger() {
    const container = document.querySelector("#review-moves");
    setText("#review-move-count", `${state.currentMoves.length} moves`);

    if (!state.currentMoves.length) {
        const isWorking = ["queued", "analyzing"].includes(state.currentGame?.status);
        renderMessage(
            "#review-moves",
            isWorking ? "Stockfish is analyzing this game…" : "No moves available.",
            isWorking ? "loading-state" : "empty-state"
        );
        return;
    }

    const rows = new Map();
    state.currentMoves.forEach((move, index) => {
        if (!rows.has(move.move_number)) rows.set(move.move_number, {});
        rows.get(move.move_number)[move.side] = { move, index };
    });

    container.innerHTML = [...rows.entries()].map(([number, pair]) => `
        <div class="review-move-row">
            <span class="review-move-number">${number}.</span>
            ${reviewMoveButton(pair.white)}
            ${reviewMoveButton(pair.black)}
        </div>`).join("");
}

function reviewMoveButton(entry) {
    if (!entry) return '<span class="review-move"></span>';
    const quality = moveQuality(entry.move);
    return `
        <button class="review-move" type="button" data-review-index="${entry.index}" title="${quality.label}">
            <span class="san">${escapeHtml(entry.move.san_move)}</span>
            <span class="move-flag quality-${quality.key}">${quality.flag}</span>
        </button>`;
}

function setReviewPosition(index) {
    if (!state.currentMoves.length) {
        state.reviewIndex = -1;
        return;
    }

    state.reviewIndex = Math.max(-1, Math.min(index, state.currentMoves.length - 1));
    const currentMove = state.reviewIndex >= 0 ? state.currentMoves[state.reviewIndex] : null;
    const startingMove = state.currentMoves[0];
    const fen = currentMove ? currentMove.fen_after : startingMove.fen_before;
    const evaluation = currentMove ? currentMove.evaluation_after : startingMove.evaluation_before;
    const orientation = state.currentGame?.user_color || "white";

    renderReviewBoard(fen, orientation, currentMove);
    renderEvaluationBar(evaluation);

    document.querySelectorAll("[data-review-index]").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.reviewIndex) === state.reviewIndex);
    });

    const activeMove = document.querySelector("[data-review-index].active");
    if (activeMove) activeMove.scrollIntoView({ block: "nearest" });

    const quality = moveQuality(currentMove);
    const qualityElement = document.querySelector("#review-quality");
    qualityElement.className = `move-quality quality-${quality.key}`;
    qualityElement.textContent = quality.label;

    setText("#review-current-move", currentMove ? `${currentMove.move_number}${currentMove.side === "black" ? "…" : "."} ${currentMove.san_move}` : "Starting position");
    setText("#review-current-evaluation", formatEvaluation(evaluation));
    setText("#review-progress", state.reviewIndex < 0 ? "Start" : `${state.reviewIndex + 1} / ${state.currentMoves.length}`);
    setText("#review-best-move", currentMove?.best_move || "—");
    setText("#review-engine-line", currentMove?.principal_variation?.join(" ") || "—");

    document.querySelector("#review-first").disabled = state.reviewIndex < 0;
    document.querySelector("#review-previous").disabled = state.reviewIndex < 0;
    document.querySelector("#review-next").disabled = state.reviewIndex >= state.currentMoves.length - 1;
    document.querySelector("#review-last").disabled = state.reviewIndex >= state.currentMoves.length - 1;
}

function renderReviewBoard(fen, orientation, currentMove) {
    const board = parseFen(fen);
    const files = orientation === "black" ? "hgfedcba" : "abcdefgh";
    const ranks = orientation === "black" ? "12345678" : "87654321";
    const lastMove = currentMove?.uci_move;
    const highlighted = lastMove ? [lastMove.slice(0, 2), lastMove.slice(2, 4)] : [];
    const destination = lastMove?.slice(2, 4);
    const quality = currentMove ? moveQuality(currentMove) : null;
    const container = document.querySelector("#review-chessboard");
    container.innerHTML = "";

    for (const rank of ranks) {
        for (const file of files) {
            const squareName = `${file}${rank}`;
            const square = document.createElement("div");
            square.className = `square ${isDarkSquare(file, rank) ? "dark" : ""} ${highlighted.includes(squareName) ? "last-move" : ""}`;
            square.dataset.square = squareName;
            const qualityBadge = squareName === destination && quality
                ? `<span class="board-move-badge quality-${quality.key}" title="${quality.label}" aria-label="${quality.label}">${quality.flag}</span>`
                : "";
            square.innerHTML = `${pieceMarkup(board[squareName])}${qualityBadge}${boardCoordinates(file, rank, files, ranks)}`;
            container.append(square);
        }
    }
}

function renderEvaluationBar(value) {
    const score = value ?? 0;
    const boundedScore = Math.max(-2000, Math.min(2000, score));
    const whiteShare = 100 / (1 + Math.exp(-boundedScore / 350));
    document.querySelector("#evaluation-white").style.height = `${whiteShare}%`;
    const bar = document.querySelector(".evaluation-bar");
    bar.classList.toggle("light-score", whiteShare >= 50);
    setText("#review-evaluation", formatEvaluation(value));
}

function moveQuality(move) {
    if (!move?.classification) return { key: "neutral", label: "Start", flag: "—" };
    const labels = {
        best: { key: "best", label: "Best", flag: "★" },
        good: { key: "good", label: "Good", flag: "✓" },
        inaccuracy: { key: "inaccuracy", label: "Inaccuracy", flag: "?!" },
        mistake: { key: "mistake", label: "Mistake", flag: "?" },
        blunder: { key: "blunder", label: "Blunder", flag: "??" },
    };
    return labels[move.classification] || { key: "neutral", label: "Unrated", flag: "—" };
}

function manageAnalysisPolling(game) {
    stopPolling();
    if (!["queued", "analyzing"].includes(game.status)) return;
    state.pollTimer = window.setInterval(async () => {
        await openAnalysis(game.id, true);
        await loadGames();
    }, 2000);
}

function stopPolling() {
    if (state.pollTimer) window.clearInterval(state.pollTimer);
    state.pollTimer = null;
}

function closeAnalysis() {
    stopPolling();
    state.currentGame = null;
    state.currentMoves = [];
    state.currentStats = null;
    state.reviewIndex = -1;
    document.querySelector("#analysis-panel").classList.add("hidden");
    document.querySelector(".games-recent-panel").classList.remove("hidden");
    switchView("games");
}

async function reanalyzeCurrentGame() {
    if (state.currentGame) await queueAnalysis(state.currentGame.id);
}

async function queueAnalysis(gameId) {
    try {
        await request(`/games/${gameId}/analyze`, { method: "POST" });
        showNotice(`Game ${gameId} was sent for analysis.`);
        await loadGames();
        await openAnalysis(gameId);
    } catch (error) {
        showNotice(error.message, true);
    }
}

async function uploadGame(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const button = document.querySelector("#upload-button");
    const file = document.querySelector("#pgn-file").files[0];
    const pgnText = document.querySelector("#pgn-text").value.trim();
    const chessComLink = document.querySelector("#chess-com-link").value.trim();
    if (state.uploadMode === "link" && !chessComLink) {
        showNotice("Paste a Chess.com game link first.", true);
        return;
    }
    if (state.uploadMode === "file" && !file) {
        showNotice("Choose a PGN file first.", true);
        return;
    }
    if (state.uploadMode === "text" && !pgnText) {
        showNotice("Paste PGN text first.", true);
        return;
    }

    const formData = new FormData();
    const selectedColor = form.querySelector('[name="user_color"]:checked').value;
    formData.append("user_color", selectedColor);
    let endpoint = "/games";
    if (state.uploadMode === "link") {
        endpoint = "/games/from-chess-com";
        formData.append("url", chessComLink);
    } else if (state.uploadMode === "text") {
        formData.append("file", new Blob([pgnText], { type: "text/plain" }), "pasted-game.pgn");
    } else {
        formData.append("file", file);
    }
    button.disabled = true;
    button.textContent = "Uploading…";
    try {
        const game = await request(endpoint, { method: "POST", body: formData });
        showNotice(`Game ${game.id} uploaded. Analysis started.`);
        form.reset();
        document.querySelector("#chess-com-link").value = "";
        document.querySelector("#pgn-text").value = "";
        setUploadMode("link");
        updateFileLabel(null);
        await loadGames();
        await openAnalysis(game.id);
    } catch (error) {
        showNotice(error.message, true);
    } finally {
        button.disabled = false;
        button.textContent = "Analyze game";
    }
}

function pieceMarkup(piece) {
    const code = pieceImageCodes[piece];
    if (!code) return "";
    return `<img class="board-piece" src="${pieceImageBaseUrl}/${code}.png" alt="" draggable="false">`;
}

function boardCoordinates(file, rank, files, ranks) {
    const rankLabel = file === files[0] ? `<span class="coordinate rank-coordinate">${rank}</span>` : "";
    const fileLabel = rank === ranks[ranks.length - 1] ? `<span class="coordinate file-coordinate">${file}</span>` : "";
    return rankLabel + fileLabel;
}

function parseFen(fen) {
    const result = {};
    const rows = fen.split(" ")[0].split("/");
    rows.forEach((row, rowIndex) => {
        let fileIndex = 0;
        for (const token of row) {
            if (/\d/.test(token)) {
                fileIndex += Number(token);
            } else {
                result[`${"abcdefgh"[fileIndex]}${8 - rowIndex}`] = token;
                fileIndex += 1;
            }
        }
    });
    return result;
}

function switchView(viewName) {
    if (!pageCopy[viewName]) return;
    state.currentView = viewName;
    document.body.dataset.view = viewName;
    document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
    document.querySelector(`#${viewName}-view`).classList.add("active");
    document.querySelectorAll("[data-view-target]").forEach((button) => {
        button.classList.toggle("active", button.dataset.viewTarget === viewName);
    });
    setText("#page-eyebrow", pageCopy[viewName][0]);
    setText("#page-title", pageCopy[viewName][1]);
    window.location.hash = viewName;
    window.scrollTo({ top: 0, behavior: "smooth" });
}

async function request(url, options = {}) {
    const response = await fetch(url, options);
    const contentType = response.headers.get("content-type") || "";
    const data = contentType.includes("application/json") ? await response.json() : null;
    if (!response.ok) {
        const detail = data?.detail;
        const message = Array.isArray(detail)
            ? detail.map((item) => item.msg).join("; ")
            : detail || `Request failed (${response.status})`;
        throw new Error(message);
    }
    return data;
}

function showNotice(message, isError = false) {
    const notice = document.querySelector("#global-notice");
    notice.textContent = message;
    notice.className = `notice ${isError ? "error" : ""}`;
    window.clearTimeout(showNotice.timer);
    showNotice.timer = window.setTimeout(() => notice.classList.add("hidden"), 4500);
}

function updateFileLabel(file) {
    setText("#file-label", file ? file.name : "Drop a PGN file or browse");
}

function setText(selector, value) {
    const element = document.querySelector(selector);
    if (element) element.textContent = value;
}

function renderMessage(selector, message, className) {
    const element = document.querySelector(selector);
    const content = escapeHtml(message);
    element.innerHTML = `<div class="${className}">${content}</div>`;
}

function playerName(name, elo) {
    const rating = elo == null ? "" : ` <em>(${escapeHtml(elo)})</em>`;
    return `${escapeHtml(name)}${rating}`;
}

function formatDate(value) {
    if (!value) return "No date";
    return new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function formatEvaluation(value) {
    if (value === null || value === undefined) return "—";
    if (value >= 99000) return "+M";
    if (value <= -99000) return "−M";
    const pawns = value / 100;
    return `${pawns > 0 ? "+" : ""}${pawns.toFixed(2)}`;
}

function isDarkSquare(file, rank) {
    return ("abcdefgh".indexOf(file) + Number(rank)) % 2 === 1;
}

function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, (character) => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
    })[character]);
}
