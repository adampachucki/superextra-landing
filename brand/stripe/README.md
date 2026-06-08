# Stripe brand assets

Upload targets for **dashboard.stripe.com → Settings → Branding** (set in **both** live and test mode).

| File                  | Spec                                   | Stripe field          |
| --------------------- | -------------------------------------- | --------------------- |
| `superextra-icon.png` | 512×512, black mark on cream `#fefdf9` | **Icon** (square)     |
| `superextra-logo.png` | 1760×480, transparent wordmark         | **Logo** (non-square) |

Companion settings: **Brand color** `#1a1a1a`, **Accent color** `#fefdf9`, Checkout font **Inter**.

## Regenerate

Rendered from the brand mark (`static/favicon.svg`) and navbar wordmark (Inter Light) via headless Chrome:

```sh
cd brand/stripe
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --default-background-color=00000000 --window-size=512,512 \
  --screenshot=superextra-icon.png "file://$PWD/icon.html"
sips -z 512 512 superextra-icon.png
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --default-background-color=00000000 --window-size=880,240 \
  --screenshot=superextra-logo.png "file://$PWD/logo.html"
```

These are source/upload assets only — not deployed (they do **not** belong in `static/`).
