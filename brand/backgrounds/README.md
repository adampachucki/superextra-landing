# Backgrounds — the only three

Every brand surface uses one of these. No patterns, no glitch, no other gradients.

| Background           | Value                                          | Wordmark        |
| -------------------- | ---------------------------------------------- | --------------- |
| **White**            | cream `#fefdf9`                                | ink `#1a1a1a`   |
| **Black**            | `#141210`                                      | cream `#fefdf9` |
| **Colorful + noise** | brand canvas gradient + film grain & scanlines | cream `#fefdf9` |

The colorful gradient is the hero canvas palette (`src/lib/canvas-helpers.ts`) with the noise overlay (grain at 0.55 `overlay` blend + faint scanlines).

Tagline, when shown: **AI consultant for every restaurant** (no "An").

## Regenerate

`cover.html` renders any of the three at 1640×624 with the wordmark + tagline:

```sh
cd brand/backgrounds
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
sb() { "$CHROME" --headless=new --disable-gpu --hide-scrollbars \
  --window-size=1640,624 --virtual-time-budget=2200 --screenshot="$1" "file://$PWD/cover.html?$2"; }
sb bg-white.png "bg=white"
sb bg-black.png "bg=black"
sb bg-color-noise.png "bg=color&s=3"   # s = gradient seed
```

Source/upload assets only — not deployed.
