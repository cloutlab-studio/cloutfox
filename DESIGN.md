# Design

Brutal 2.0: the Brutal universe of cloutlab.studio, tuned for a tool people use all day. Tokens live in `frontend/src/styles/tokens.css` (`--t-*` are the site's own values; the rest are the app's states). Never add a hex value outside that file.

## Look

- Paper `--t-bg` `#F5F0E1` with a faint dot grid, white sheets, black ink `#0A0A0A`; the rail is black.
- Square corners everywhere. Rules are black: 3px around sheets, dialogs and under table headers, 2px on fields and buttons, 1px between rows.
- Raised blocks cast a hard offset shadow with no blur (`--t-hard`, `6px 6px 0`). Dialogs `10px`; a danger dialog's shadow is red, an alert's is pink.
- Yellow `--t-accent` only on things you can press and on the active filter, page or segment; pink `--t-accent-2` on hover. Text on yellow is black.
- Blue `--live` is the live state: running rows (left bar, tint), the live stamp, the running counter, focus rings, Stop's hover.
- Red `--error` only for failures and destructive actions.
- Type: Inter Tight Black, uppercase, tracking `-0.04em` for page and dialog titles (`.display`); Inter Tight for UI text; IBM Plex Mono for data cells, labels, buttons and the log. Both ship in `src/assets/fonts/` with their OFL licences and cover Cyrillic.
- User data keeps its case: never put profile names, tags or reasons in an uppercase style (titles carry a generic word, the name goes in the subtitle).
- Status reads by form as well as colour: live is a rotated double-rule stamp, starting a dashed rule, failed a struck red rule.
- Every data cell in a profile row keeps two lines. A narrow window drops the geo column first (container query on the sheet).

## Motion

- Easing is the site's spring `--t-ease` (`cubic-bezier(.34,1.56,.64,1)`), `--t-dur` 0.38s; `--t-ease-out` for things that only fade in.
- Buttons lift on hover (shadow grows) and press flat into their shadow on click.
- Rows cascade in on load and on a new filter or search (only the first ~18 wait). Page titles drop in letter by letter. The live stamp lands with a spring; a failure shakes once.
- `data-motion="reduced"` on `<html>` (system setting or Settings → Interface) cuts every animation and transition to nothing. The custom cursor then turns off too.
- Looping animations change only `transform` or `opacity` and read `--loops` (paused while the window is in the background). A loop on any other property (`outline-offset`, `background-position`, colours) redraws the page every frame: it costs CPU, and in Qt WebEngine each frame's garbage stays in Blink's heap until `lib/gc.ts` collects it. To move a pattern, put it on a pseudo-element one period wider and translate it by a period.

## Sound

- Synthesised in `frontend/src/lib/sound.ts` (Web Audio): no sound files.
- Voices: `tap`, `toggle`, `open`/`close` (sheets), `launch`, `live` (stamp thud), `stop`, `error`, `done` (warm-up, backup, export), `help`.
- Each voice has a minimum gap (`GAPS`), so a bulk launch is one sound. Sound follows Settings (on by default, volume); `help` always plays.

## Cursor

The studio cursor: a square dot and a lagging square ring with a hard shadow that turns yellow over anything pressable (`[data-press]`, buttons, labels). Only with a mouse, with motion on, and while Settings keep it on. Text fields keep the text caret.
