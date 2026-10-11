# Local opening theory

`openings.json` maps EPD positions to theoretical UCI moves. Position identity
includes side to move, castling rights and legally available en passant;
clocks and fullmove numbers are excluded. This is a finite repertoire, not a
database of every sound opening move. No network request is needed for review.

The analyzer also indexes the resulting positions, including terminal positions,
and verifies short reordered sequences against the moves of an actual book path.
After an unrecognized move, Book classification stops for the rest of the game.

## Supplemental lines

The Sicilian Kan Wing Attack continuation below extends the existing prefix
through `6...Bb7 7.O-O`:

```pgn
1. e4 c5 2. Nf3 e6 3. d4 cxd4 4. Nxd4 a6 5. Nc3 b5 6. Bd3 Bb7 7. O-O
```

Reference: the Chess.com `ECOUrl` opening identifier supplied in the imported PGN
for game 11, [Kan Knight Variation Wing Attack](https://www.chess.com/openings/Sicilian-Defense-Kan-Knight-Variation-Wing-Attack-6.Bd3-Bb7-7.O-O).
The added edges are `c8b7` after `6.Bd3` and `e1g1` after `6...Bb7`.
The original `6...Qb6` continuation remains available. Game headers are not used
to classify moves at runtime: the complete legal board position must match this
local file, including for games without an ECO header.
