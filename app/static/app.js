const state = {
    games: [],
    currentView: "dashboard",
    currentGame: null,
    currentMoves: [],
    currentStats: null,
    initialClockSeconds: null,
    reviewIndex: -1,
    pollTimer: null,
    analysisRequest: 0,
    totalMoves: 0,
    startingFen: null,
    boardOrientation: "white",
    candidateCache: new Map(),
    candidateKey: null,
    candidateTimer: null,
    candidateController: null,
    candidateRequest: 0,
    playerCountries: new Map(),
    playerCountryRequests: new Set(),
    renderedBoard: null,
    boardAnimations: new Set(),
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
const pieceMoveDuration = 200;
const navigableMoveQualities = new Set(["brilliant", "great", "blunder", "miss"]);

const moveQualities = [
    ["brilliant", "Brilliant"], ["great", "Great"], ["book", "Book"],
    ["best", "Best"], ["excellent", "Excellent"], ["good", "Good"],
    ["inaccuracy", "Inaccuracy"], ["mistake", "Mistake"],
    ["miss", "Miss"], ["blunder", "Blunder"],
].map(([key, label]) => ({ key, label,
    flag: `<img class="quality-icon" src="/static/assets/move-quality/${key}.png" alt="" width="22" height="22">`,
}));

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
    document.querySelector("#flip-board-button").addEventListener("click", () => {
        state.boardOrientation = state.boardOrientation === "white" ? "black" : "white";
        renderPlayerStatistics();
        setReviewPosition(state.reviewIndex);
    });

    document.querySelector("#review-first").addEventListener("click", () => setReviewPosition(-1));
    document.querySelector("#review-previous").addEventListener("click", () => setReviewPosition(state.reviewIndex - 1));
    document.querySelector("#review-next").addEventListener("click", () => setReviewPosition(state.reviewIndex + 1));
    document.querySelector("#review-last").addEventListener("click", () => setReviewPosition(state.currentMoves.length - 1));
    document.querySelector("#review-moves").addEventListener("click", (event) => {
        const moveButton = event.target.closest("[data-review-index]");
        if (moveButton) setReviewPosition(Number(moveButton.dataset.reviewIndex));
    });
    document.querySelector("#review-quality-summary").addEventListener("click", (event) => {
        const button = event.target.closest("[data-quality-index]");
        if (button && !button.disabled) setReviewPosition(Number(button.dataset.qualityIndex));
    });

    document.addEventListener("keydown", (event) => {
        const isTyping = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
        const panelIsOpen = !document.querySelector("#analysis-panel").classList.contains("hidden");
        if (isTyping || state.currentView !== "games" || !panelIsOpen) return;
        if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            setReviewPosition(state.reviewIndex + (event.key === "ArrowLeft" ? -1 : 1));
        }
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
    if (quiet && state.currentGame?.id !== gameId) return;
    const requestId = ++state.analysisRequest;
    if (!quiet) switchView("games");
    const panel = document.querySelector("#analysis-panel");
    document.querySelector(".games-recent-panel").classList.add("hidden");
    panel.classList.remove("hidden");
    document.body.dataset.reviewOpen = "true";
    if (!quiet) {
        stopPolling();
        const selectedGame = state.games.find((game) => game.id === gameId);
        setText("#analysis-title", selectedGame
            ? `${selectedGame.white_player} — ${selectedGame.black_player}` : "Game analysis");
        setText("#analysis-meta", "Loading analysis…");
        renderMessage("#review-moves", "Loading Stockfish moves…", "loading-state");
        if (state.currentGame?.id !== gameId) {
            stopBoardAnimations();
            state.renderedBoard = null;
            stopCandidateReview();
            state.currentGame = null;
            state.currentMoves = [];
            state.currentStats = null;
            state.reviewIndex = -1;
            state.startingFen = null;
            state.boardOrientation = "white";
            renderPlayerStatistics();
            document.querySelector("#review-chessboard").replaceChildren();
        }
    }

    try {
        const [game, analysis] = await Promise.all([
            request(`/games/${gameId}`),
            request(`/games/${gameId}/analysis`),
        ]);
        if (requestId !== state.analysisRequest) return;
        const isSameGame = state.currentGame?.id === game.id;
        state.currentGame = game;
        state.currentMoves = analysis.moves;
        state.totalMoves = analysis.total_moves ?? analysis.moves.length;
        state.startingFen = analysis.starting_fen ?? analysis.moves[0]?.fen_before ?? null;
        state.initialClockSeconds = analysis.initial_clock_seconds ?? null;
        state.currentStats = {
            white: analysis.white_stats,
            black: analysis.black_stats,
        };
        if (!isSameGame || state.reviewIndex >= state.currentMoves.length) state.reviewIndex = -1;
        renderAnalysis(quiet);
        loadPlayerFlags(game);
        if (!quiet) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        manageAnalysisPolling(game);
    } catch (error) {
        if (requestId !== state.analysisRequest) return;
        setText("#analysis-meta", error.message);
        if (!quiet) renderMessage("#review-moves", error.message, "empty-state");
        if (quiet && state.currentGame?.id === gameId) manageAnalysisPolling(state.currentGame);
    }
}

function renderAnalysis(quiet = false) {
    const game = state.currentGame;
    if (!game) return;
    document.querySelector("#reanalyze-button").disabled = ["queued", "analyzing"].includes(game.status);
    setText("#analysis-title", `${game.white_player} — ${game.black_player}`);
    setText(
        "#analysis-meta",
        `${game.result} · ${engineLabels[game.engine] || game.engine} · ${statusLabels[game.status] || game.status} · ${formatDate(game.played_at || game.created_at)}`
    );

    renderPlayerStatistics();
    renderQualitySummary();
    renderMoveLedger();
    setReviewPosition(state.reviewIndex, !quiet);
}

function renderPlayerStatistics() {
    if (!state.currentGame) {
        document.querySelector("#top-player").innerHTML = "";
        document.querySelector("#bottom-player").innerHTML = "";
        return;
    }

    const bottomColor = state.boardOrientation;
    const topColor = bottomColor === "white" ? "black" : "white";
    document.querySelector("#top-player").innerHTML = playerBoardLabel(
        topColor,
        state.currentStats?.[topColor],
        topColor === state.currentGame.user_color ? "You" : "Opponent"
    );
    document.querySelector("#bottom-player").innerHTML = playerBoardLabel(
        bottomColor,
        state.currentStats?.[bottomColor],
        bottomColor === state.currentGame.user_color ? "You" : "Opponent"
    );
}

function playerBoardLabel(color, stats, role) {
    const game = state.currentGame;
    const name = color === "white" ? game.white_player : game.black_player;
    const elo = color === "white" ? game.white_elo : game.black_elo;
    const accuracy = stats?.accuracy == null ? "—" : `${stats.accuracy}%`;
    return `
        <div class="board-player-info"><div class="board-player-identity" title="${escapeHtml(name)} · ${role} · ${color}">
            <div><span class="player-country-flag-slot" data-player-flag="${color}">${playerFlagMarkup(color)}</span><strong>${playerName(name, elo)}</strong><small>${role} · ${escapeHtml(color)}</small></div>
        </div>
        <div class="board-player-stats" title="Estimated accuracy from expected points lost; not Chess.com CAPS">
            <div class="player-stat stat-accuracy" title="Accuracy"><b>${accuracy}</b><small>Accuracy</small></div>
            ${[["inaccuracy", "inaccuracies"], ["mistake", "mistakes"], ["blunder", "blunders"]].map(([key, field]) => {
                const quality = moveQualities.find((item) => item.key === key);
                const count = stats?.accuracy == null ? "—" : stats[field] ?? 0;
                return `<div class="player-stat stat-${key}" title="${quality.label}: ${count}">${quality.flag}<b>${count}</b><small class="sr-only">${quality.label}</small></div>`;
            }).join("")}
        </div></div>
        <div class="player-clock clock-${color}" data-clock-color="${color}" role="timer" aria-live="off" aria-label="${color} time remaining">
            <svg class="clock-face" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 6v6l4 2" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
            <span>${formatClock(state.initialClockSeconds)}</span>
        </div>`;
}

function playerFlagMarkup(color) {
    const country = state.playerCountries.get(`${state.currentGame?.id}:${color}`);
    if (typeof country !== "string" || !/^[A-Z]{2}$/.test(country)) return "";
    let label = country;
    try {
        label = new Intl.DisplayNames(["en"], { type: "region" }).of(country) || country;
    } catch { /* The country code remains readable in older browsers. */ }
    return `<img class="player-country-flag" src="/static/assets/flags/${country.toLowerCase()}.svg" width="20" height="15" alt="${escapeHtml(label)} flag" title="${escapeHtml(label)}">`;
}

async function loadPlayerFlags(game) {
    if (state.playerCountryRequests.has(game.id)) return;
    state.playerCountryRequests.add(game.id);
    try {
        const countries = await request(`/games/${game.id}/players`);
        state.playerCountries.set(`${game.id}:white`, countries.white_country);
        state.playerCountries.set(`${game.id}:black`, countries.black_country);
        if (state.currentGame?.id !== game.id) return;
        document.querySelectorAll("[data-player-flag]").forEach((slot) => {
            slot.innerHTML = playerFlagMarkup(slot.dataset.playerFlag);
        });
    } catch {
        // An unavailable profile must not interfere with game review.
        state.playerCountryRequests.delete(game.id);
    }
}

function formatClock(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return "—";
    const tenths = Math.max(0, Math.round(seconds * 10));
    const whole = Math.floor(tenths / 10);
    const minutes = Math.floor(whole / 60);
    const secondsPart = String(whole % 60).padStart(2, "0");
    if (tenths < 100) return `0:${secondsPart}.${tenths % 10}`;
    if (minutes >= 60) return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}:${secondsPart}`;
    return `${minutes}:${secondsPart}`;
}

function formatThinkingTime(seconds) {
    if (seconds == null || !Number.isFinite(seconds)) return "—";
    const tenths = Math.max(0, Math.round(seconds * 10));
    if (tenths < 600) return `${tenths / 10}s`;
    const whole = Math.floor(tenths / 10);
    return `${Math.floor(whole / 60)}m ${String(whole % 60).padStart(2, "0")}s`;
}

function renderPlayerClocks(fen) {
    const clocks = { white: state.initialClockSeconds, black: state.initialClockSeconds };
    for (let i = 0; i <= state.reviewIndex; i++) {
        const move = state.currentMoves[i];
        clocks[move.side] = move.clock_seconds ?? null;
    }
    const turn = fen?.split(" ")[1] === "b" ? "black" : "white";
    const finished = state.reviewIndex === state.totalMoves - 1 && state.currentGame?.result !== "*";
    document.querySelectorAll("[data-clock-color]").forEach((clock) => {
        const color = clock.dataset.clockColor;
        const text = formatClock(clocks[color]);
        clock.querySelector("span").textContent = text;
        clock.classList.toggle("is-active", !finished && color === turn);
        clock.classList.toggle("clock-unavailable", clocks[color] == null);
        clock.setAttribute("aria-label", `${color} time remaining: ${text}`);
    });
}

function renderQualitySummary() {
    const counts = { white: {}, black: {} };
    const firstMoves = { white: {}, black: {} };
    state.currentMoves.forEach((move, index) => {
        if (counts[move.side] && move.classification) {
            counts[move.side][move.classification] = (counts[move.side][move.classification] || 0) + 1;
            firstMoves[move.side][move.classification] ??= index;
        }
    });
    document.querySelector("#review-quality-summary").innerHTML = `
        <summary>Move classifications <span>White / Black</span></summary>
        <table aria-label="Move classifications by player">
            <thead><tr><th scope="col">Classification</th><th scope="col">White</th><th scope="col"><span class="sr-only">Icon</span></th><th scope="col">Black</th></tr></thead>
            <tbody>${moveQualities.map((quality) => `
                <tr class="summary-${quality.key}"><th scope="row">${quality.label}</th>
                <td>${qualitySummaryCount(quality, "white", counts.white[quality.key] || 0, firstMoves.white[quality.key])}</td><td>${quality.flag}</td>
                <td>${qualitySummaryCount(quality, "black", counts.black[quality.key] || 0, firstMoves.black[quality.key])}</td></tr>`).join("")}</tbody>
        </table>`;
}

function qualitySummaryCount(quality, side, count, index) {
    if (!navigableMoveQualities.has(quality.key)) return String(count);
    const player = side === "white" ? "White" : "Black";
    const label = count ? `${player}: first ${quality.label} move, ${count} total`
        : `${player}: no ${quality.label} moves`;
    return `<button class="quality-jump" type="button" data-quality-index="${index ?? -1}"
        ${count ? "" : "disabled"} title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${count}</button>`;
}

function renderMoveLedger() {
    const container = document.querySelector("#review-moves");
    const isWorking = ["queued", "analyzing"].includes(state.currentGame?.status);
    setText("#review-move-count", isWorking
        ? `${state.currentMoves.length} / ${state.totalMoves} analyzed` : `${state.currentMoves.length} moves`);
    const progress = document.querySelector("#analysis-progress");
    progress.classList.toggle("hidden", !isWorking);
    setText("#analysis-progress-label", state.currentGame?.status === "queued" ? "Waiting for Stockfish…"
        : `Stockfish · ${state.currentMoves.length} / ${state.totalMoves} moves analyzed`);
    const meter = document.querySelector("#analysis-progress-meter");
    meter.max = Math.max(1, state.totalMoves);
    meter.value = state.currentMoves.length;

    if (!state.currentMoves.length) {
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
        <button class="review-move${quality.key === "brilliant" ? " is-brilliant" : ""}" type="button" data-review-index="${entry.index}" title="${quality.label}" aria-label="${escapeHtml(entry.move.san_move)}: ${quality.label}, thinking time ${formatThinkingTime(entry.move.thinking_time_seconds)}">
            <span class="san">${escapeHtml(entry.move.san_move)}</span>
            <span class="move-thinking-time" title="Thinking time${entry.move.thinking_time_seconds == null ? ' unavailable' : `: ${entry.move.thinking_time_seconds} seconds`}">${formatThinkingTime(entry.move.thinking_time_seconds)}</span>
            <span class="move-flag quality-${quality.key}">${quality.flag}</span>
        </button>`;
}

function setReviewPosition(index, scrollActive = true) {
    state.reviewIndex = Math.max(-1, Math.min(index, state.currentMoves.length - 1));
    const currentMove = state.reviewIndex >= 0 ? state.currentMoves[state.reviewIndex] : null;
    const startingMove = state.currentMoves[0];
    const fen = currentMove ? currentMove.fen_after : state.startingFen || startingMove?.fen_before;
    const evaluation = currentMove ? currentMove.evaluation_after : startingMove?.evaluation_before;
    const orientation = state.boardOrientation;

    if (fen) renderReviewBoard(fen, orientation, currentMove);
    renderEvaluationBar(evaluation);
    renderPlayerClocks(fen);

    document.querySelectorAll("[data-review-index]").forEach((button) => {
        button.classList.toggle("active", Number(button.dataset.reviewIndex) === state.reviewIndex);
    });

    const activeMove = document.querySelector("[data-review-index].active");
    if (activeMove && scrollActive) activeMove.scrollIntoView({ block: "nearest" });

    const quality = moveQuality(currentMove);
    const qualityElement = document.querySelector("#review-quality");
    qualityElement.className = `move-quality quality-${quality.key}`;
    qualityElement.innerHTML = `${quality.flag}<span>${quality.label}</span>`;

    setText("#review-current-move", currentMove ? `${currentMove.move_number}${currentMove.side === "black" ? "…" : "."} ${currentMove.san_move}` : "Starting position");
    setText("#review-current-evaluation", formatEvaluation(evaluation));
    setText("#review-progress", state.reviewIndex < 0 ? "Start" : `${state.reviewIndex + 1} / ${state.currentMoves.length}`);

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
    const previous = state.renderedBoard;
    const sameBoard = previous?.orientation === orientation && previous.gameId === state.currentGame?.id;
    if (!sameBoard) {
        stopBoardAnimations();
        container.replaceChildren();
        const squares = new Map();
        const pieces = new Map();
        for (const rank of ranks) {
            for (const file of files) {
                const squareName = `${file}${rank}`;
                const square = document.createElement("div");
                square.className = `square${isDarkSquare(file, rank) ? " dark" : ""}`;
                square.dataset.square = squareName;
                square.innerHTML = `${pieceMarkup(board[squareName])}${boardCoordinates(file, rank, files, ranks)}`;
                container.append(square);
                squares.set(squareName, square);
                const piece = square.querySelector(".board-piece");
                if (piece) pieces.set(squareName, piece);
            }
        }
        state.renderedBoard = { gameId: state.currentGame?.id, orientation, board, squares, pieces,
            index: state.reviewIndex };
    } else {
        const direction = state.reviewIndex - previous.index;
        const step = direction === 1 ? currentMove : direction === -1 ? state.currentMoves[previous.index] : null;
        const transitions = planPieceTransitions(previous.board, board, step?.uci_move, direction);
        updateBoardPieces(container, previous, board, transitions);
        previous.board = board;
        previous.index = state.reviewIndex;
    }

    for (const [squareName, square] of state.renderedBoard.squares) {
        square.classList.toggle("last-move", highlighted.includes(squareName));
        square.querySelector(".board-move-badge")?.remove();
        if (squareName === destination && quality) {
            square.insertAdjacentHTML("beforeend", `<span class="board-move-badge quality-${quality.key}" title="${quality.label}" aria-label="${quality.label}">${quality.flag}</span>`);
        }
    }
    container.querySelector(".best-move-arrows")?.remove();
    const nextMove = state.currentMoves[state.reviewIndex + 1];
    const candidateKey = `${state.currentGame?.id}:${state.reviewIndex + 1}`;
    const candidates = state.candidateCache.has(candidateKey) ? state.candidateCache.get(candidateKey)
        : nextMove?.candidate_moves?.length ? nextMove.candidate_moves
        : nextMove?.best_move ? [nextMove.best_move] : [];
    const arrows = bestMoveArrows(candidates, files, ranks, board);
    if (arrows) container.insertAdjacentHTML("beforeend", arrows);
    if (!state.candidateCache.has(candidateKey) && (nextMove?.candidate_moves?.length ?? 0) < 3) {
        loadReviewCandidates(fen);
    }
}

function planPieceTransitions(before, after, uci, direction) {
    const removed = new Set(Object.keys(before).filter((square) => before[square] !== after[square]));
    const added = new Set(Object.keys(after).filter((square) => before[square] !== after[square]));
    const moves = [];
    const pair = (from, to) => {
        moves.push({ from, to, piece: after[to] });
        removed.delete(from);
        added.delete(to);
    };
    if (uci && Math.abs(direction) === 1) {
        const from = direction === 1 ? uci.slice(0, 2) : uci.slice(2, 4);
        const to = direction === 1 ? uci.slice(2, 4) : uci.slice(0, 2);
        if (removed.has(from) && added.has(to)) pair(from, to);
    }
    // Remaining equal pieces include the rook during castling, and pieces moved
    // when jumping across several moves in the notation.
    const candidates = [];
    for (const from of removed) {
        for (const to of added) {
            if (before[from] === after[to]) candidates.push({ from, to,
                distance: (from.charCodeAt(0) - to.charCodeAt(0)) ** 2 + (Number(from[1]) - Number(to[1])) ** 2 });
        }
    }
    candidates.sort((a, b) => a.distance - b.distance);
    for (const { from, to } of candidates) {
        if (removed.has(from) && added.has(to)) pair(from, to);
    }
    return { moves, removed: [...removed], added: [...added] };
}

function stopBoardAnimations() {
    for (const animation of state.boardAnimations) animation.cancel();
    state.boardAnimations.clear();
}

function cancelPieceAnimation(piece) {
    if (piece.reviewAnimation) {
        state.boardAnimations.delete(piece.reviewAnimation);
        piece.reviewAnimation.cancel();
        piece.reviewAnimation = null;
    }
    piece.classList.remove("piece-moving");
}

function animateBoardPiece(piece, frames, duration, finish = () => {}) {
    const animation = piece.animate(frames, { duration, easing: "cubic-bezier(.25,.1,.25,1)" });
    piece.reviewAnimation = animation;
    state.boardAnimations.add(animation);
    animation.finished.then(() => {
        state.boardAnimations.delete(animation);
        if (piece.reviewAnimation !== animation) return;
        piece.reviewAnimation = null;
        piece.classList.remove("piece-moving");
        finish();
    }, () => {
        state.boardAnimations.delete(animation);
    });
}

function updateBoardPieces(container, previous, board, transitions) {
    if (!transitions.moves.length && !transitions.removed.length && !transitions.added.length) return;
    // Board motion is explicitly requested: system reduced-motion preferences
    // must not silently disable this feature.
    const animate = typeof container.animate === "function";
    // Sample displayed positions before cancelling, so a fast reversal continues
    // from the piece's current position rather than its previous target square.
    const snapshots = new Map();
    const targets = new Map();
    const boardRect = container.getBoundingClientRect();
    for (const square of new Set([...transitions.moves.map((move) => move.from), ...transitions.removed])) {
        const piece = previous.pieces.get(square);
        if (piece) snapshots.set(square, { piece, rect: piece.getBoundingClientRect(),
            opacity: window.getComputedStyle(piece).opacity });
    }
    for (const move of transitions.moves) targets.set(move.to, previous.squares.get(move.to).getBoundingClientRect());
    for (const ghost of container.querySelectorAll(".piece-exit")) {
        cancelPieceAnimation(ghost);
        ghost.remove();
    }
    const pieces = new Map(previous.pieces);
    for (const { from } of transitions.moves) pieces.delete(from);
    for (const square of transitions.removed) {
        const snapshot = snapshots.get(square);
        pieces.delete(square);
        if (!snapshot) continue;
        const { piece, rect, opacity } = snapshot;
        cancelPieceAnimation(piece);
        if (!animate) { piece.remove(); continue; }
        piece.classList.add("piece-exit");
        Object.assign(piece.style, { left: `${rect.left - boardRect.left}px`, top: `${rect.top - boardRect.top}px`,
            width: `${rect.width}px`, height: `${rect.height}px` });
        container.append(piece);
        animateBoardPiece(piece, [{ opacity }, { opacity: 0 }], 90, () => piece.remove());
    }
    for (const { from, to, piece: code } of transitions.moves) {
        const snapshot = snapshots.get(from);
        if (!snapshot) continue;
        const { piece, rect } = snapshot;
        cancelPieceAnimation(piece);
        previous.squares.get(to).append(piece);
        pieces.set(to, piece);
        const finish = () => { piece.src = `${pieceImageBaseUrl}/${pieceImageCodes[code]}.png`; };
        const target = targets.get(to);
        const dx = rect.left - target.left;
        const dy = rect.top - target.top;
        if (animate && Math.hypot(dx, dy) > 0.5) {
            piece.classList.add("piece-moving");
            animateBoardPiece(piece, [
                { transform: `translate(${dx}px, ${dy}px)` }, { transform: "translate(0px, 0px)" },
            ], pieceMoveDuration, finish);
        } else finish();
    }
    for (const square of transitions.added) {
        previous.squares.get(square).insertAdjacentHTML("afterbegin", pieceMarkup(board[square]));
        const piece = previous.squares.get(square).querySelector(".board-piece");
        pieces.set(square, piece);
        if (animate) animateBoardPiece(piece, [{ opacity: 0 }, { opacity: 1 }], 90);
    }
    previous.pieces = pieces;
}

function stopCandidateReview(clearCache = false) {
    state.candidateRequest++;
    if (state.candidateTimer) window.clearTimeout(state.candidateTimer);
    state.candidateController?.abort();
    state.candidateTimer = null;
    state.candidateController = null;
    state.candidateKey = null;
    if (clearCache) state.candidateCache.clear();
}

function loadReviewCandidates(fen) {
    if (!state.currentGame) return;
    const gameId = state.currentGame.id;
    const ply = state.reviewIndex + 1;
    const key = `${gameId}:${ply}`;
    if (state.candidateKey === key) return;
    stopCandidateReview();
    state.candidateKey = key;
    const requestId = state.candidateRequest;
    const isCurrent = () => requestId === state.candidateRequest && state.currentGame?.id === gameId
        && state.reviewIndex + 1 === ply;
    const run = async () => {
        if (!isCurrent()) return;
        state.candidateController = new AbortController();
        try {
            const response = await request(`/games/${gameId}/candidates?ply=${ply}`,
                { signal: state.candidateController.signal });
            if (!isCurrent()) return;
            if (!response.ready) {
                state.candidateTimer = window.setTimeout(run, 500);
                return;
            }
            state.candidateCache.set(key, response.candidate_moves);
            const orientation = state.boardOrientation;
            const arrows = bestMoveArrows(response.candidate_moves,
                orientation === "black" ? "hgfedcba" : "abcdefgh",
                orientation === "black" ? "12345678" : "87654321", parseFen(fen));
            const container = document.querySelector("#review-chessboard");
            container.querySelector(".best-move-arrows")?.remove();
            if (arrows) container.insertAdjacentHTML("beforeend", arrows);
        } catch (error) {
            if (isCurrent() && error.name !== "AbortError") state.candidateKey = null;
        }
    };
    state.candidateTimer = window.setTimeout(run, 180);
}

function bestMoveArrows(candidates, files, ranks, board) {
    const colors = ["#39c5bb", "#a3a8b0", "#a3a8b0"];
    const roots = [...new Set(candidates.map((move) => move.slice(0, 4)))].slice(0, 3);
    if (!roots.length) return "";
    const paths = roots.map((move, index) => {
        const [fromFile, fromRank, toFile, toRank] = move;
        const x1 = files.indexOf(fromFile) * 100 + 50;
        const y1 = ranks.indexOf(fromRank) * 100 + 50;
        const x2 = files.indexOf(toFile) * 100 + 50;
        const y2 = ranks.indexOf(toRank) * 100 + 50;
        if ([x1, y1, x2, y2].some((coordinate) => coordinate < 0)) return "";
        let path = `M ${x1} ${y1} L ${x2} ${y2}`;
        let length = Math.hypot(x2 - x1, y2 - y1);
        if (board[fromFile + fromRank]?.toLowerCase() === "n") {
            length = Math.abs(x2 - x1) + Math.abs(y2 - y1);
            path = Math.abs(x2 - x1) > Math.abs(y2 - y1)
                ? `M ${x1} ${y1} L ${x2} ${y1} L ${x2} ${y2}`
                : `M ${x1} ${y1} L ${x1} ${y2} L ${x2} ${y2}`;
        }
        // Leave the final 45 units for the arrowhead so translucent fills never
        // overlap the shaft and create a darker dot inside the tip.
        return `<path d="${path}" stroke="${colors[index]}" stroke-width="${17 - index * 3}" stroke-dasharray="${Math.max(0, length - 45)} 45" opacity="${index === 0 ? .55 : .32}" marker-end="url(#best-arrow-${index})"/>`;
    }).reverse().join("");
    return `<svg class="best-move-arrows" viewBox="0 0 800 800" role="img" aria-label="Best moves: ${roots.map(escapeHtml).join(", ")}">
        <defs>${colors.map((color, index) => `<marker id="best-arrow-${index}" markerUnits="userSpaceOnUse" markerWidth="45" markerHeight="45" refX="45" refY="22.5" orient="auto"><path d="M 0 0 L 45 22.5 L 0 45 Z" fill="${color}"/></marker>`).join("")}</defs>
        <g fill="none" stroke-linecap="butt" stroke-linejoin="round">${paths}</g></svg>`;
}

function renderEvaluationBar(value) {
    const score = value ?? 0;
    const boundedScore = Math.max(-2000, Math.min(2000, score));
    const whiteShare = 100 / (1 + Math.exp(-boundedScore / 350));
    document.querySelector("#evaluation-white").style.height = `${whiteShare}%`;
    const bar = document.querySelector(".evaluation-bar");
    bar.classList.toggle("black-bottom", state.boardOrientation === "black");
    bar.classList.toggle("light-score", whiteShare >= 50);
    setText("#review-evaluation", formatEvaluation(value));
}

function moveQuality(move) {
    if (!move?.classification) return { key: "neutral", label: "Start", flag: "—" };
    return moveQualities.find((quality) => quality.key === move.classification)
        || { key: "neutral", label: "Unrated", flag: "—" };
}

function manageAnalysisPolling(game) {
    stopPolling();
    if (!["queued", "analyzing"].includes(game.status)) return;
    state.pollTimer = window.setTimeout(async () => {
        state.pollTimer = null;
        if (state.currentGame?.id !== game.id) return;
        await openAnalysis(game.id, true);
        await loadGames();
    }, 500);
}

function stopPolling() {
    if (state.pollTimer) window.clearTimeout(state.pollTimer);
    state.pollTimer = null;
}

function closeAnalysis() {
    stopBoardAnimations();
    state.renderedBoard = null;
    stopCandidateReview();
    state.analysisRequest++;
    document.body.dataset.reviewOpen = "false";
    stopPolling();
    state.currentGame = null;
    state.currentMoves = [];
    state.currentStats = null;
    state.initialClockSeconds = null;
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
        stopCandidateReview(true);
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
    if (element && element.textContent !== String(value)) element.textContent = value;
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
