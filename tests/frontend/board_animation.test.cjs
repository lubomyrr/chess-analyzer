const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function boardContext(reduced = false) {
    const context = vm.createContext({
        document: { addEventListener() {} },
        window: { matchMedia: () => ({ matches: reduced }), getComputedStyle: () => ({ opacity: '1' }) },
    });
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../../app/static/app.js'), 'utf8')
        + '\nglobalThis.reviewState = state;', context);
    return context;
}

function plan(before, after, uci, direction) {
    const context = boardContext();
    Object.assign(context, { before, after, uci, direction });
    return JSON.parse(JSON.stringify(vm.runInContext('planPieceTransitions(before, after, uci, direction)', context)));
}

test('ordinary moves and captures identify the moving piece and victim in both directions', () => {
    assert.deepEqual(plan({ e2: 'P' }, { e4: 'P' }, 'e2e4', 1), {
        moves: [{ from: 'e2', to: 'e4', piece: 'P' }], removed: [], added: [],
    });
    assert.deepEqual(plan({ e4: 'P', d5: 'p' }, { d5: 'P' }, 'e4d5', 1), {
        moves: [{ from: 'e4', to: 'd5', piece: 'P' }], removed: ['d5'], added: [],
    });
    assert.deepEqual(plan({ d5: 'P' }, { e4: 'P', d5: 'p' }, 'e4d5', -1), {
        moves: [{ from: 'd5', to: 'e4', piece: 'P' }], removed: [], added: ['d5'],
    });
});

test('castling moves king and rook together, including reverse and Black queenside', () => {
    assert.deepEqual(plan({ e1: 'K', h1: 'R' }, { g1: 'K', f1: 'R' }, 'e1g1', 1).moves, [
        { from: 'e1', to: 'g1', piece: 'K' }, { from: 'h1', to: 'f1', piece: 'R' },
    ]);
    assert.deepEqual(plan({ g1: 'K', f1: 'R' }, { e1: 'K', h1: 'R' }, 'e1g1', -1).moves, [
        { from: 'g1', to: 'e1', piece: 'K' }, { from: 'f1', to: 'h1', piece: 'R' },
    ]);
    assert.deepEqual(plan({ e8: 'k', a8: 'r' }, { c8: 'k', d8: 'r' }, 'e8c8', 1).moves, [
        { from: 'e8', to: 'c8', piece: 'k' }, { from: 'a8', to: 'd8', piece: 'r' },
    ]);
});

test('en passant fades the off-destination pawn and restores it when stepping back', () => {
    assert.deepEqual(plan({ e5: 'P', d5: 'p' }, { d6: 'P' }, 'e5d6', 1), {
        moves: [{ from: 'e5', to: 'd6', piece: 'P' }], removed: ['d5'], added: [],
    });
    assert.deepEqual(plan({ d6: 'P' }, { e5: 'P', d5: 'p' }, 'e5d6', -1), {
        moves: [{ from: 'd6', to: 'e5', piece: 'P' }], removed: [], added: ['d5'],
    });
});

test('promotion carries the pawn to its new piece and reverses correctly after a capture', () => {
    assert.deepEqual(plan({ a7: 'P', b8: 'r' }, { b8: 'N' }, 'a7b8n', 1), {
        moves: [{ from: 'a7', to: 'b8', piece: 'N' }], removed: ['b8'], added: [],
    });
    assert.deepEqual(plan({ b8: 'N' }, { a7: 'P', b8: 'r' }, 'a7b8n', -1), {
        moves: [{ from: 'b8', to: 'a7', piece: 'P' }], removed: [], added: ['b8'],
    });
});

test('jumps animate changed pieces without moving stationary pieces', () => {
    const result = plan({ e2: 'P', g1: 'N', a1: 'R' }, { e4: 'P', f3: 'N', a1: 'R' }, null, 7);
    assert.equal(result.moves.length, 2);
    assert.deepEqual(result.removed, []);
    assert.deepEqual(result.added, []);
    assert.equal(result.moves.some(move => move.from === 'a1'), false);
});

function animatedPiece(rect) {
    const animations = [];
    const classes = new Set(['piece-moving']);
    const piece = {
        style: {}, src: '/static/assets/pieces/wp.png',
        classList: { add: c => classes.add(c), remove: c => classes.delete(c) },
        getBoundingClientRect: () => rect,
        animate(frames, options) {
            let finish, reject;
            const animation = {
                frames, options,
                finished: new Promise((res, rej) => { finish = res; reject = rej; }),
                cancel: () => reject(new Error('Cancelled')), finish: () => finish(),
            };
            animations.push(animation);
            return animation;
        },
    };
    return { piece, animations, classes };
}

test('rapid reversal reuses the image and starts from its displayed position', async () => {
    const context = boardContext();
    const { piece, animations } = animatedPiece({ left: 450, top: 540, width: 100, height: 100 });
    context.piece = piece;
    vm.runInContext('animateBoardPiece(piece, [], 160, () => { piece.src = "obsolete"; })', context);
    context.container = { animate() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }), querySelectorAll: () => [] };
    context.previous = {
        pieces: new Map([['e4', piece]]),
        squares: new Map([['e2', { append(p) { assert.equal(p, piece); },
            getBoundingClientRect: () => ({ left: 450, top: 650 }) }]]),
    };
    vm.runInContext('updateBoardPieces(container, previous, {e2:"P"}, {moves:[{from:"e4",to:"e2",piece:"P"}],removed:[],added:[]})', context);
    await Promise.resolve();
    assert.equal(animations.length, 2);
    assert.equal(context.reviewState.boardAnimations.size, 1);
    assert.equal(animations[1].frames[0].transform, 'translate(0px, -110px)');
    assert.equal(animations[1].options.duration, 200);
    assert.equal(context.previous.pieces.get('e2'), piece);
    animations[1].finish();
    await Promise.resolve();
    assert.equal(piece.src, '/static/assets/pieces/wp.png');
    assert.equal(context.reviewState.boardAnimations.size, 0);
});

test('explicit board animation runs even with reduced-motion and survives background refresh', async () => {
    const context = boardContext(true);
    context.container = { animate() {}, getBoundingClientRect: () => ({ left: 0, top: 0 }), querySelectorAll: () => [] };
    const { piece, animations } = animatedPiece({ left: 0, top: 0 });
    context.previous = { pieces: new Map([['a7', piece]]), squares: new Map([['a8', {
        append() {}, getBoundingClientRect: () => ({ left: 0, top: 100 }),
    }]]) };
    vm.runInContext('updateBoardPieces(container, previous, {a8:"Q"}, {moves:[{from:"a7",to:"a8",piece:"Q"}],removed:[],added:[]})', context);
    assert.equal(animations.length, 1);
    assert.equal(animations[0].options.duration, 200);
    assert.equal(piece.src, '/static/assets/pieces/wp.png');
    context.container.getBoundingClientRect = () => assert.fail('Unchanged board must not be rebuilt');
    vm.runInContext('updateBoardPieces(container, previous, {}, {moves:[],removed:[],added:[]})', context);
    assert.equal(context.reviewState.boardAnimations.size, 1);
    animations[0].finish();
    await Promise.resolve();
    assert.equal(piece.src, '/static/assets/pieces/wq.png');
});
