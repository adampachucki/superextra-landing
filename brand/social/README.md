# Social & profile assets

Identity assets (profile photos + banners) for social platforms. Cream `#fefdf9` background, mark/text `#1a1a1a`, Inter Light wordmark with the mark raised to match the site navbar/footer. All rendered at **2× for retina**.

| Platform    | File                    | Pixels    | Display size    | Use                           |
| ----------- | ----------------------- | --------- | --------------- | ----------------------------- |
| Instagram   | `instagram-profile.png` | 1200×1200 | crops to circle | Profile photo                 |
| LinkedIn    | `linkedin-logo.png`     | 1200×1200 | square          | Company page logo             |
| LinkedIn    | `linkedin-banner.png`   | 2256×382  | 1128×191        | Page banner                   |
| X / Twitter | `x-profile.png`         | 1200×1200 | crops to circle | Profile photo                 |
| X / Twitter | `x-header.png`          | 3000×1000 | 1500×500        | Header                        |
| Google      | `google-logo.png`       | 1200×1200 | square          | Business / responsive-ad logo |
| Google      | `google-landscape.png`  | 2400×1256 | 1200×628        | Landscape brand image         |
| Facebook    | `fb-profile.png`        | 1080×1080 | crops to circle | Profile photo                 |
| Facebook    | `fb-cover.png`          | 1640×624  | 820×312         | Cover photo                   |

Square profiles use a circle-safe mark (~45% width, generous margin). Banners keep the wordmark + tagline in the center safe zone (X overlays the avatar bottom-left; LinkedIn/FB crop on mobile).

## Regenerate

Rendered via headless Chrome (`--force-device-scale-factor=2`). Source templates: `_square.html` (profiles) and `_banner.html` (parametrized: `?w=&h=&word=&tag=`, mark proportions auto-derived from the word font size).

```sh
cd brand/social
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
shot() { "$CHROME" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 \
  --window-size=$1,$2 --screenshot="$3" "file://$PWD/$4"; }

shot 600 600 instagram-profile.png _square.html
shot 1128 191 linkedin-banner.png "_banner.html?w=1128&h=191&word=64&tag=20"
shot 1500 500 x-header.png        "_banner.html?w=1500&h=500&word=96&tag=30"
shot 1200 628 google-landscape.png "_banner.html?w=1200&h=628&word=72&tag=24"
```

Source/upload assets only — not deployed.
