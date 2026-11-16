# Track & Cover

A small Windows desktop MP3 tag editor for reviewing catalog matches, filling verified metadata, embedding cover art, and saving a PNG copy of the cover.

The application source is licensed under GPL-2.0-or-later. Third-party license notices are in `licenses` (summary: `licenses/THIRD-PARTY-NOTICES.md`) and are included in the built executable.

## Start the app from source

1. Install Python 3.11 or newer from python.org and select the option to add Python to PATH.
2. Open PowerShell in this folder.
3. Run `py -3 -m venv .venv`.
4. Run `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
5. Run `.\.venv\Scripts\python.exe app.py`.

## Build a standalone Windows app

Run `build_windows.ps1` in PowerShell. The finished app is `dist\TrackAndCover.exe` and does not require Python to launch.

## How it works

- Choose a folder; the app scans MP3 files in that folder (not subfolders).
- Select a song and search MusicBrainz, with Apple's public catalog as a fallback.
- Review the match before applying it. The app does not batch-edit a folder automatically.
- The default setting fills blank fields only. Turn that setting off to replace existing values with the selected match.
- Before changing an MP3, the app copies the original to `%LOCALAPPDATA%\Track & Cover\Backups`.
- Cover art comes from MusicBrainz's Cover Art Archive or the Apple catalog fallback. Where available, the app requests a 1200-pixel image, embeds it in the MP3, and saves a PNG in an `Album Art` folder.
- Lyrics: open the **Lyrics** tab next to the match details and choose **Get lyrics**. Lyrics come from LRCLIB (lrclib.net, a free, open lyrics database), matched by title, artist and song length. When you apply, they are saved in the MP3's standard lyrics tag (USLT). With "Only fill blank fields" on, existing lyrics are kept. Nothing is written if you don't fetch lyrics.
- Composer is only filled when the selected catalog record supplies a composer credit. Apple catalog fallback results do not supply composer credits.
- If the catalog match is uncertain or no cover exists, review the song details and leave unsupported fields blank.

## Interface ("Aqua Night" theme)

- The UI lives in `ui/`: `theme.py` (colours, fonts, Pillow renderers), `aero_widgets.py` (glossy buttons, toggles, table/list styling, bubble background) and `main_view.py` (window layout). `app.py` only wires the view to the app logic.
- Fonts: Exo 2 and Nunito Sans are bundled in `assets/fonts/` (SIL Open Font License, see `licenses/Exo2-OFL.txt` and `licenses/NunitoSans-OFL.txt`); the app falls back to Segoe UI if they can't be loaded.
- The drifting background bubbles can be switched off with **Animate background** (remembered in `%LOCALAPPDATA%\Track & Cover\settings.json`). The animation also pauses while the window is minimised or unfocused, and starts off if Windows animation effects are turned off.
- Keyboard: Tab / Shift+Tab move through fields, buttons and toggles; Space or Enter activates the focused button or toggle.

## Website (GitHub Pages)

The download page lives in `docs/` (`docs/index.html` plus `docs/assets/`). To publish it:

1. Upload the project to a public GitHub repository (the `docs` folder included).
2. Publish a Release and attach `dist\TrackAndCover.exe`. The file must be named exactly `TrackAndCover.exe`, because the page's Download buttons point to `releases/latest/download/TrackAndCover.exe`.
3. In the repository: **Settings → Pages → Build and deployment → Source: Deploy from a branch**, then **Branch: main, Folder: /docs**, and **Save**.
4. After a minute the site is live at `https://<your-username>.github.io/<repository-name>/`.

On a `github.io` address the page fills in your GitHub username and repository for its links automatically. Elsewhere (your own domain, Netlify, Cloudflare Pages) the links point to `BlueBird-117/track-and-cover`, as written in `docs/index.html`.

## Data sources and rate limits

MusicBrainz asks applications to identify themselves with a User-Agent that includes a contact, and to limit requests to one per second. Track & Cover identifies itself and spaces MusicBrainz searches accordingly. When the project has a public home (for example its GitHub repository), set `PROJECT_URL` near the top of `app.py` so it's included in the User-Agent. Cover images are fetched through the Cover Art Archive or the Apple catalog's high-resolution artwork URLs.

This is a personal-use starter build. You remain responsible for reviewing proposed matches and ensuring any use of downloaded artwork complies with applicable rights.
