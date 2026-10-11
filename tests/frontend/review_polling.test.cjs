const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

function review() {
    const elements = new Map();
    const timers = new Map();
    let timerId = 0;
    const document = {
        body: { dataset: {} },
        addEventListener() {},
        querySelectorAll() { return []; },
        querySelector(selector) {
            if (!elements.has(selector)) elements.set(selector, {
                textContent: "", innerHTML: "", classList: { add() {}, remove() {} },
                scrollIntoView() {}, replaceChildren() {},
                addEventListener() {},
                querySelector() { return null; },
                insertAdjacentHTML(position, html) { this.innerHTML += html; },
            });
            return elements.get(selector);
        },
    };
    const context = vm.createContext({ document, AbortController, window: {
        setTimeout(callback) { timers.set(++timerId, callback); return timerId; },
        clearTimeout(id) { timers.delete(id); },
    } });
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../../app/static/app.js"), "utf8"), context);
    vm.runInContext(`
        globalThis.pending = new Map();
        request = (url) => new Promise((resolve) => pending.set(url, resolve));
        switchView = () => {};
        renderAnalysis = () => setText("#analysis-title", state.currentGame.white_player + " — " + state.currentGame.black_player);
        globalThis.reviewState = state;
    `, context);
    return { context, elements, document, timers };
}

function finish(context, game) {
    context.pending.get(`/games/${game.id}`)(game);
    context.pending.get(`/games/${game.id}/analysis`)({ moves: [1, 2, 3], total_moves: 127 });
}

test("background polling preserves the title, displayed moves and selected position", async () => {
    const { context, document } = review();
    const game = { id: 10, white_player: "dipresseded", black_player: "MixUman", status: "analyzing" };
    context.reviewState.currentGame = game;
    context.reviewState.reviewIndex = 1;
    document.querySelector("#analysis-title").textContent = "dipresseded — MixUman";
    document.querySelector("#review-moves").innerHTML = "Displayed moves";
    const poll = vm.runInContext("openAnalysis(10, true)", context);
    assert.equal(document.querySelector("#analysis-title").textContent, "dipresseded — MixUman");
    assert.equal(document.querySelector("#review-moves").innerHTML, "Displayed moves");
    finish(context, game);
    await poll;
    assert.equal(context.reviewState.reviewIndex, 1);
});

test("a late poll cannot replace another game opened in the meantime", async () => {
    const { context } = review();
    const oldGame = { id: 10, white_player: "First", black_player: "Second", status: "analyzing" };
    const newGame = { ...oldGame, id: 11, status: "completed" };
    context.reviewState.currentGame = oldGame;
    context.reviewState.games = [oldGame, newGame];
    const poll = vm.runInContext("openAnalysis(10, true)", context);
    const opening = vm.runInContext("openAnalysis(11)", context);
    finish(context, newGame);
    await opening;
    finish(context, oldGame);
    await poll;
    assert.equal(context.reviewState.currentGame.id, 11);
});

test("closing analysis cancels application of an in-flight response", async () => {
    const { context } = review();
    const game = { id: 10, status: "analyzing" };
    context.reviewState.currentGame = game;
    const poll = vm.runInContext("openAnalysis(10, true)", context);
    vm.runInContext("closeAnalysis()", context);
    finish(context, game);
    await poll;
    assert.equal(context.reviewState.currentGame, null);
});

test("candidate arrows point to the same chess squares in either orientation", () => {
    const { context } = review();
    const white = vm.runInContext('bestMoveArrows(["e2e4", "d2d4", "g1f3"], "abcdefgh", "87654321", { g1: "N" })', context);
    assert.match(white, /M 450 650 L 450 450/);
    assert.match(white, /M 650 750 L 650 550 L 550 550/);
    assert.match(white, /Best moves: e2e4, d2d4, g1f3/);
    const black = vm.runInContext('bestMoveArrows(["e2e4"], "hgfedcba", "12345678", {})', context);
    assert.match(black, /M 350 150 L 350 350/);
    assert.equal(vm.runInContext('bestMoveArrows([], "abcdefgh", "87654321", {})', context), "");
});

test("quick navigation debounces requests and ignores late suggestions for an old position", async () => {
    const { context, timers, document } = review();
    context.reviewState.currentGame = { id: 10 };
    context.reviewState.reviewIndex = 0;
    const fen = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
    context.testFen = fen;
    vm.runInContext('loadReviewCandidates(testFen)', context);
    const [firstId, firstCallback] = timers.entries().next().value;
    timers.delete(firstId);
    const first = firstCallback();
    context.reviewState.reviewIndex = 1;
    vm.runInContext('loadReviewCandidates(testFen)', context);
    context.reviewState.reviewIndex = 2;
    vm.runInContext('loadReviewCandidates(testFen)', context);
    assert.equal(timers.size, 1);
    context.pending.get('/games/10/candidates?ply=1')({ ready: true, candidate_moves: ['d2d4'] });
    await first;
    assert.equal(context.reviewState.candidateCache.has('10:1'), false);
    const [lastId, lastCallback] = timers.entries().next().value;
    timers.delete(lastId);
    const last = lastCallback();
    context.reviewState.boardOrientation = 'black';
    context.pending.get('/games/10/candidates?ply=3')({ ready: true, candidate_moves: ['e2e4','d2d4','g1f3'] });
    await last;
    assert.equal(context.reviewState.candidateCache.get('10:3').length, 3);
    assert.match(document.querySelector('#review-chessboard').innerHTML, /M 350 150 L 350 350/);
});

test("flags use local assets, preserve colors and ignore stale game responses", async () => {
    const { context, document } = review();
    const slots = [
        { dataset: { playerFlag: 'white' }, innerHTML: '' },
        { dataset: { playerFlag: 'black' }, innerHTML: '' },
    ];
    document.querySelectorAll = () => slots;
    context.reviewState.currentGame = { id: 10 };
    const flags = vm.runInContext('loadPlayerFlags({id:10})', context);
    await vm.runInContext('loadPlayerFlags({id:10})', context);
    assert.equal(context.pending.size, 1);
    context.pending.get('/games/10/players')({ white_country: 'US', black_country: 'GB' });
    await flags;
    assert.match(slots[0].innerHTML, /\/static\/assets\/flags\/us.svg/);
    assert.match(slots[1].innerHTML, /\/static\/assets\/flags\/gb.svg/);
    const old = vm.runInContext('loadPlayerFlags({id:11})', context);
    context.pending.get('/games/11/players')({ white_country: 'FR', black_country: 'DE' });
    await old;
    assert.match(slots[0].innerHTML, /\/us.svg/);
    context.reviewState.playerCountries.set('10:white', '<script>');
    assert.equal(vm.runInContext('playerFlagMarkup("white")', context), '');
});

test("classification counters link to the first matching move of each player", () => {
    const { context, document } = review();
    context.reviewState.currentMoves = [
        {side:'white',classification:'brilliant'},
        {side:'black',classification:'brilliant'},
        {side:'white',classification:'great'},
        {side:'black',classification:'blunder'},
        {side:'white',classification:'brilliant'},
        {side:'black',classification:'miss'},
        {side:'white',classification:'blunder'},
        {side:'black',classification:'brilliant'},
    ];
    vm.runInContext('renderQualitySummary()', context);
    const html = document.querySelector('#review-quality-summary').innerHTML;
    assert.match(html, /data-quality-index="0"[^>]*aria-label="White: first Brilliant move, 2 total"/);
    assert.match(html, /data-quality-index="1"[^>]*aria-label="Black: first Brilliant move, 2 total"/);
    assert.match(html, /data-quality-index="2"[^>]*aria-label="White: first Great move, 1 total"/);
    assert.match(html, /data-quality-index="3"[^>]*aria-label="Black: first Blunder move, 1 total"/);
    assert.match(html, /data-quality-index="5"[^>]*aria-label="Black: first Miss move, 1 total"/);
    assert.match(html, /data-quality-index="6"[^>]*aria-label="White: first Blunder move, 1 total"/);
    assert.match(html, /data-quality-index="-1"\s+disabled[^>]*aria-label="White: no Miss moves"/);
    assert.equal(vm.runInContext('qualitySummaryCount({key:"good",label:"Good"},"white",2,9)', context), '2');
});

test("clicking a classification counter navigates, while a disabled zero is ignored", () => {
    const { context, document } = review();
    let onClick;
    document.querySelector('#review-quality-summary').addEventListener = (event, fn) => {
        if (event === 'click') onClick = fn;
    };
    vm.runInContext('setReviewPosition = (index) => { globalThis.selectedQualityIndex = index; }; bindGames();', context);
    onClick({target:{closest:()=>({disabled:false,dataset:{qualityIndex:'7'}})}});
    assert.equal(context.selectedQualityIndex, 7);
    onClick({target:{closest:()=>({disabled:true,dataset:{qualityIndex:'-1'}})}});
    assert.equal(context.selectedQualityIndex, 7);
    onClick({target:{closest:()=>null}});
    assert.equal(context.selectedQualityIndex, 7);
});
