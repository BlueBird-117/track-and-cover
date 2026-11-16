# Track & Cover 2.0 Beta: Source and Upgrade Guide

This guide explains what is in the source package, how to run or rebuild the app, and where to make design or feature changes.

## 1. What you need

- A Windows laptop.
- Python 3.11 or newer installed from python.org, with the Python launcher (`py`) and `pip` available.
- An internet connection for installing packages and for searching music catalogs and artwork.

The source ZIP contains the Python code and build instructions. It does not contain the temporary test song or build cache.

## 2. Extract and open the project

1. Extract `TrackAndCover-2.0-Beta-source.zip` to a normal folder, such as `Documents\TrackAndCover`.
2. Open that folder in File Explorer.
3. Click the address bar, type `powershell`, and press Enter. PowerShell opens in the project folder.

## 3. Run the app from source

In that PowerShell window, enter these commands one at a time:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

The first command creates a private Python environment for this project. The second installs the libraries the app needs. The third starts the app. You only need to create `.venv` once per extracted project folder.

If Windows says `py` is not recognized, install Python from python.org and select the option to install the Python launcher. You can also open `build_windows.ps1` by right-clicking it and choosing **Run with PowerShell** after Python is installed.

## 4. Build a new standalone app

After changing the source, run `build_windows.ps1` from PowerShell in the project folder:

```powershell
.\build_windows.ps1
```

The build script creates or prepares `.venv`, installs the dependencies, and packages the app. The finished executable is:

```text
dist\TrackAndCover.exe
```

The build requires internet access to download dependencies. It builds a Windows app; it does not create a Mac or Linux version.

## 5. What each file does

| File | Purpose |
| --- | --- |
| `app.py` | The app itself: screen layout, catalog search, artwork preview, and MP3 tag writing. |
| `requirements.txt` | Lists the Python libraries needed to run and build the app. |
| `build_windows.ps1` | Automates dependency installation and creates the standalone Windows executable. |
| `README.md` | Short project overview and basic run/build information. |
| `LICENSE` | License for the app source code. |
| `licenses/` | License notices for included third-party libraries. |

## 6. How the code is organized

Everything is currently in `app.py`:

- **`TrackFile`** reads the existing title, artist, album, year, and genre tags from an MP3.
- **`Candidate`** holds one possible catalog match and the details the app may write to the song.
- **`Catalog`** searches MusicBrainz and Apple's catalog, ranks likely matches, and retrieves cover art. MusicBrainz covers are requested from the Cover Art Archive; Apple search results can supply a high-resolution image too.
- **`TrackAndCoverApp`** builds the screen and connects the buttons to search, preview, and save actions.
- **`_write_track()`** backs up the selected MP3, writes the supported ID3 fields, embeds cover art, and can save a PNG copy.
- **`main()`** starts the desktop window.

The app asks you to review a match before applying it. By default it fills blank fields only. Before saving, it makes a backup under `%LOCALAPPDATA%\Track & Cover\Backups`.

## 7. Where to make common changes

### Change how the app looks

Open `app.py` and find **`_build_ui()`** inside `TrackAndCoverApp`.

- The window size is set near the start of `TrackAndCoverApp.__init__()` with `geometry()` and `minsize()`.
- Colors, fonts, and button spacing are set near the start of `_build_ui()` using `ttk.Style`.
- Screen areas, labels, inputs, and buttons are created in the rest of `_build_ui()`.
- The album image preview is controlled by `_drain_events()` in the section that handles the `cover` event.

Make one small visual change at a time, run the app from source, and check the layout at both normal and maximized window sizes.

### Change catalog search

Look at **`Catalog.search()`**, **`_musicbrainz_candidates()`**, and **`_itunes_candidates()`**. Search changes can affect which result appears first, so check several songs with different artists and titles before rebuilding.

### Change metadata fields

Look at **`_write_track()`** and its ID3 frame mapping. The current app supports title, artist, album artist, album, genre, composer, track number, year, release date, and embedded artwork when the chosen catalog result supplies those values.

Keep uncertain values blank. Avoid changing the default “Only fill blank fields” behavior unless you specifically want the app to overwrite existing tags.

### Change artwork handling

Look at **`Catalog.cover_for()`** for downloading and validating cover images, and the `cover` block in **`_write_track()`** for embedding the image and saving the PNG copy.

## 8. A safe upgrade routine

1. Make a copy of the project folder before editing it.
2. Make your changes in the copy.
3. Run the app from source and try it on a separate folder containing a copy of a song.
4. Confirm the match, metadata, embedded artwork, PNG copy, and backup are correct.
5. Run `build_windows.ps1` to create a new executable.
6. Keep the previous executable until the new one has worked on your laptop.

Do not use your only copy of a song for testing. The app has a backup feature, but a separate test copy makes it easier to check changes safely.

## 9. If something goes wrong

- **`py` is not recognized:** Install Python and its launcher, then reopen PowerShell.
- **Package installation fails:** Check your internet connection and try the install command again.
- **Catalog search reports a connection error:** Check that the laptop can access the internet. Catalog search and artwork download both need a connection.
- **A match is missing or looks wrong:** Try a clearer title or artist search, inspect the displayed match, and do not apply it unless it is the right recording.
- **The standalone build fails:** Read the last error shown in PowerShell. The source-run commands in section 3 can help separate a code issue from a packaging issue.

