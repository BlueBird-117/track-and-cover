from __future__ import annotations

import io
import json
import math
import os
import queue
import re
import shutil
import ssl
import sys
import certifi
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from PIL import Image, ImageTk
from ui.main_view import AquaNightView
from ui.theme import enable_dpi_awareness, register_fonts
from mutagen.id3 import (APIC, ID3, TALB, TCOM, TCON, TDRC, TDRL, TIT2,
                         TPE1, TPE2, TRCK, USLT, ID3NoHeaderError)
from mutagen.mp3 import MP3


APP_NAME = "Track & Cover"
APP_VERSION = "0.1.0"
MB_URL = "https://musicbrainz.org/ws/2/recording/"
CAA_URL = "https://coverartarchive.org"
ITUNES_URL = "https://itunes.apple.com/search"
LRCLIB_URL = "https://lrclib.net/api/search"  # free, open lyrics database (no API key)
USER_AGENT = f"TrackAndCover/{APP_VERSION} (personal desktop MP3 tag editor)"


def https_context() -> ssl.SSLContext:
    # A frozen Windows build may not have OpenSSL's default CA bundle path.
    return ssl.create_default_context(cafile=certifi.where())


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", clean(value).casefold()).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalized(a), normalized(b)).ratio()


def frame_text(tags: ID3, frame_id: str) -> str:
    frame = tags.get(frame_id)
    if frame is None or not getattr(frame, "text", None):
        return ""
    return clean(str(frame.text[0]))


@dataclass
class TrackFile:
    path: Path
    title: str = ""
    artist: str = ""
    album: str = ""
    year: str = ""
    genre: str = ""

    @classmethod
    def read(cls, path: Path) -> "TrackFile":
        try:
            tags = ID3(path)
        except ID3NoHeaderError:
            tags = ID3()
        return cls(path, frame_text(tags, "TIT2"), frame_text(tags, "TPE1"),
                   frame_text(tags, "TALB"), frame_text(tags, "TDRC")[:4],
                   frame_text(tags, "TCON"))


@dataclass
class Candidate:
    source: str
    title: str
    artist: str
    album: str = ""
    album_artist: str = ""
    release_date: str = ""
    year: str = ""
    genre: str = ""
    composer: str = ""
    track_number: str = ""
    release_id: str = ""
    release_group_id: str = ""
    recording_id: str = ""
    source_url: str = ""
    score: float = 0.0
    artwork_url: str = ""

    def display(self) -> str:
        album = f" · {self.album}" if self.album else ""
        return f"{self.artist} — {self.title}{album}  [{self.source}, {self.score:.0%}]"


class Catalog:
    def __init__(self) -> None:
        self._last_mb_request = 0.0
        self.last_errors: list[str] = []

    @staticmethod
    def _get_json(url: str) -> dict:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                        "Accept": "application/json"})
        with urllib.request.urlopen(request, timeout=25, context=https_context()) as response:
            return json.loads(response.read().decode("utf-8"))

    def search(self, title: str, artist: str) -> list[Candidate]:
        found: list[Candidate] = []
        errors: list[str] = []
        if clean(title):
            def musicbrainz_search(query: str) -> None:
                nonlocal found
                delay = 1.05 - (time.monotonic() - self._last_mb_request)
                if delay > 0:
                    time.sleep(delay)
                params = urllib.parse.urlencode({"query": query, "fmt": "json", "limit": 10,
                                                 "inc": "artists+releases+release-groups+work-rels"})
                self._last_mb_request = time.monotonic()
                data = self._get_json(MB_URL + "?" + params)
                found.extend(self._musicbrainz_candidates(data, title, artist))
            terms = [f'recording:"{clean(title)}"']
            if clean(artist):
                terms.append(f'artist:"{clean(artist)}"')
            try:
                musicbrainz_search(" AND ".join(terms))
            except Exception as exc:
                errors.append(f"MusicBrainz: {exc}")
            # Strict artist matching can miss alternate credits; retry by title alone.
            if not found and clean(artist):
                try:
                    musicbrainz_search(f'recording:"{clean(title)}"')
                except Exception as exc:
                    errors.append(f"MusicBrainz title search: {exc}")
        if not found or max((x.score for x in found), default=0) < 0.75:
            try:
                term = " ".join(part for part in (artist, title) if clean(part))
                params = urllib.parse.urlencode({"term": term, "entity": "song", "limit": 12,
                                                 "country": "us"})
                data = self._get_json(ITUNES_URL + "?" + params)
                found.extend(self._itunes_candidates(data, title, artist))
            except Exception as exc:
                errors.append(f"Apple catalog: {exc}")
        self.last_errors = errors
        unique: dict[tuple[str, str, str], Candidate] = {}
        for item in sorted(found, key=lambda c: c.score, reverse=True):
            key = (normalized(item.title), normalized(item.artist), normalized(item.album))
            if key not in unique:
                unique[key] = item
        return list(unique.values())[:15]

    @staticmethod
    def _musicbrainz_candidates(data: dict, title: str, artist: str) -> list[Candidate]:
        results = []
        for recording in data.get("recordings", []):
            name = recording.get("title", "")
            credit = recording.get("artist-credit-phrase", "")
            score = 0.68 * similarity(title, name) + 0.32 * similarity(artist, credit)
            releases = recording.get("releases", [])
            release = next((r for r in releases if r.get("date")), releases[0] if releases else {})
            release_groups = recording.get("release-groups", [])
            group = release_groups[0] if release_groups else {}
            album = release.get("title") or group.get("title", "")
            release_date = release.get("date", "") or group.get("first-release-date", "")
            genres = recording.get("genres") or recording.get("tags") or group.get("genres") or []
            genre = ""
            if genres:
                genre = (genres[0].get("name") if isinstance(genres[0], dict) else str(genres[0]))
            composers = []
            pending = [recording]
            visited: set[int] = set()
            while pending:
                entity = pending.pop()
                if id(entity) in visited:
                    continue
                visited.add(id(entity))
                for rel in entity.get("relations", []):
                    if "composer" in rel.get("type", "").casefold():
                        name_obj = rel.get("artist") or rel.get("work") or {}
                        if name_obj.get("name"):
                            composers.append(name_obj["name"])
                    if isinstance(rel.get("work"), dict):
                        pending.append(rel["work"])
            results.append(Candidate(
                "MusicBrainz", name, credit, album,
                release.get("artist-credit-phrase", "") or credit, release_date,
                release_date[:4], genre, "; ".join(dict.fromkeys(composers)),
                "", release.get("id", ""),
                group.get("id", ""), recording.get("id", ""),
                f"https://musicbrainz.org/recording/{recording.get('id', '')}", score))
        return results

    @staticmethod
    def _itunes_candidates(data: dict, title: str, artist: str) -> list[Candidate]:
        results = []
        for item in data.get("results", []):
            name, credited = item.get("trackName", ""), item.get("artistName", "")
            score = 0.68 * similarity(title, name) + 0.32 * similarity(artist, credited)
            release_date = (item.get("releaseDate", "") or "")[:10]
            results.append(Candidate(
                "Apple catalog", name, credited, item.get("collectionName", ""),
                item.get("collectionArtistName", "") or credited, release_date,
                release_date[:4], item.get("primaryGenreName", ""), "",
                str(item.get("trackNumber", "")), "", "", str(item.get("trackId", "")),
                item.get("trackViewUrl", ""), score))
            results[-1].artwork_url = item.get("artworkUrl100", "")
        return results

    @staticmethod
    def cover_for(candidate: Candidate) -> bytes:
        for identifier, endpoint in ((candidate.release_id, "release"),
                                     (candidate.release_group_id, "release-group")):
            if not identifier:
                continue
            url = f"{CAA_URL}/{endpoint}/{identifier}/front-1200"
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(request, timeout=30, context=https_context()) as response:
                    data = response.read()
                with Image.open(io.BytesIO(data)) as image:
                    image.verify()
                return data
            except (urllib.error.HTTPError, urllib.error.URLError, OSError, ValueError):
                continue
        if candidate.artwork_url:
            # Apple's 100px result artwork supports larger renditions at the same URL.
            url = re.sub(r"/\d+x\d+bb\.", "/1200x1200bb.", candidate.artwork_url)
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=30, context=https_context()) as response:
                data = response.read()
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            return data
        raise LookupError("No front-cover image was found for this catalog match.")

    def lyrics_for(self, candidate: Candidate, duration: float | None) -> tuple[str, bool]:
        """Best LRCLIB lyrics for the match. Returns (plain lyrics, instrumental)."""
        params = urllib.parse.urlencode({"track_name": clean(candidate.title),
                                         "artist_name": clean(candidate.artist)})
        results = self._get_json(LRCLIB_URL + "?" + params)
        best, best_score = None, 0.0
        for item in results if isinstance(results, list) else []:
            if not (item.get("plainLyrics") or item.get("instrumental")):
                continue
            score = (0.6 * similarity(candidate.title, item.get("trackName", ""))
                     + 0.3 * similarity(candidate.artist, item.get("artistName", "")))
            length = item.get("duration")
            if duration and length:
                # Same recording should be within a few seconds; radio edits/live versions differ more.
                score += 0.1 * max(0.0, 1 - abs(float(length) - duration) / 10)
            elif candidate.album and similarity(candidate.album, item.get("albumName", "")) > 0.8:
                score += 0.05
            if score > best_score:
                best, best_score = item, score
        if not best or best_score < 0.6:
            raise LookupError("No lyrics were found for this song.")
        if best.get("instrumental") and not best.get("plainLyrics"):
            return "", True
        return best["plainLyrics"].strip(), False


class TrackAndCoverApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1180x760")
        self.root.minsize(980, 640)
        self.catalog = Catalog()
        self.folder = tk.StringVar()
        self.status = tk.StringVar(value="Choose a folder containing MP3 files to begin.")
        self.fill_empty = tk.BooleanVar(value=True)
        self.save_png = tk.BooleanVar(value=True)
        self.query_title = tk.StringVar()
        self.query_artist = tk.StringVar()
        self.tracks: dict[str, TrackFile] = {}
        self.candidates: list[Candidate] = []
        self.selected_track: TrackFile | None = None
        self.selected_candidate: Candidate | None = None
        self.cover_bytes: bytes | None = None
        self.cover_preview = None
        self.lyrics_text: str | None = None
        self.events: queue.Queue = queue.Queue()
        self._build_ui()
        self.root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        # All presentation lives in ui/ (Aqua Night theme); this only wires it to the app logic.
        self.view = AquaNightView(
            self.root, app_name=APP_NAME, folder=self.folder, status=self.status,
            fill_empty=self.fill_empty, save_png=self.save_png,
            query_title=self.query_title, query_artist=self.query_artist,
            on_choose=self._choose_folder, on_scan=self._scan_folder, on_search=self._search_selected,
            on_cover=self._get_cover, on_lyrics=self._get_lyrics, on_apply=self._apply,
            on_track_selected=self._on_track_selected, on_candidate_selected=self._on_candidate_selected)
        self.path_entry = self.view.path_entry
        self.table = self.view.table
        self.match_list = self.view.match_list
        self.details = self.view.details
        self.cover_label = self.view.cover_label
        self.search_button = self.view.search_button
        self.cover_button = self.view.cover_button
        self.lyrics_button = self.view.lyrics_button

    def _choose_folder(self) -> None:
        chosen = filedialog.askdirectory(title="Choose a folder containing MP3 files")
        if chosen:
            self.folder.set(chosen)
            self._scan_folder()

    def _scan_folder(self) -> None:
        folder = Path(self.folder.get()).expanduser()
        if not folder.is_dir():
            messagebox.showerror(APP_NAME, "Choose an existing music folder first.")
            return
        paths = sorted(folder.glob("*.mp3"), key=lambda p: p.name.casefold())
        self.table.delete(*self.table.get_children())
        self.tracks.clear()
        for index, path in enumerate(paths):
            try:
                track = TrackFile.read(path)
            except Exception:
                track = TrackFile(path)
            key = str(index)
            self.tracks[key] = track
            self.table.insert("", "end", iid=key, values=(track.title or "—", track.artist or "—",
                                                               track.album or "—", track.year or "—"))
        self.status.set(f"Found {len(paths)} MP3 file{'s' if len(paths) != 1 else ''}.")

    def _on_track_selected(self, _event=None) -> None:
        selection = self.table.selection()
        if not selection:
            return
        self.selected_track = self.tracks.get(selection[0])
        if self.selected_track:
            title, artist = self.selected_track.title, self.selected_track.artist
            if not title:
                source_name = self.selected_track.path.stem
                if " - " in source_name and not artist:
                    artist, title = source_name.split(" - ", 1)
                else:
                    title = source_name
            self.query_title.set(title)
            self.query_artist.set(artist)
        self.candidates.clear()
        self.selected_candidate = None
        self.cover_bytes = None
        self.match_list.delete(0, "end")
        self.cover_label.configure(image="", text="Cover artwork preview appears here")
        self._show_details("Select Search catalog to look up this song.")
        self.search_button.configure(state="normal")
        self.cover_button.configure(state="disabled")
        self.lyrics_text = None
        self.lyrics_button.configure(state="disabled")
        self.view.show_lyrics(None)

    def _search_selected(self) -> None:
        if not self.selected_track:
            return
        track = self.selected_track
        title = clean(self.query_title.get())
        artist = clean(self.query_artist.get())
        if not title:
            self.status.set("Enter a song title to search.")
            return
        self.status.set(f"Searching for {title}…")
        self.search_button.configure(state="disabled")
        threading.Thread(target=self._search_worker,
                         args=(title, artist, str(track.path)), daemon=True).start()

    def _search_worker(self, title: str, artist: str, track_path: str) -> None:
        try:
            result = self.catalog.search(title, artist)
            errors = self.catalog.last_errors
        except Exception as exc:
            result, errors = [], [str(exc)]
        self.events.put(("search", (track_path, result, errors)))

    def _on_candidate_selected(self, _event=None) -> None:
        selection = self.match_list.curselection()
        if not selection or selection[0] >= len(self.candidates):
            return
        self.selected_candidate = self.candidates[selection[0]]
        c = self.selected_candidate
        self._show_details(
            f"Title: {c.title}\nArtist: {c.artist}\nAlbum: {c.album or '—'}\n"
            f"Album artist: {c.album_artist or '—'}\nRelease date: {c.release_date or '—'}\n"
            f"Genre: {c.genre or '—'}\nComposer: {c.composer or '—'}\n"
            f"Match strength: {c.score:.0%}\nSource: {c.source}")
        self.cover_button.configure(state="normal" if c.release_id or c.release_group_id or c.artwork_url else "disabled")
        self.cover_bytes = None
        self.cover_label.configure(image="", text="Choose Get cover preview to check for artwork")
        self.lyrics_text = None
        self.lyrics_button.configure(state="normal")
        self.view.show_lyrics(None)

    def _get_lyrics(self) -> None:
        candidate = self.selected_candidate
        if not candidate or not self.selected_track:
            return
        self.lyrics_button.configure(state="disabled")
        self.status.set(f"Looking for lyrics for {candidate.title}…")
        threading.Thread(target=self._lyrics_worker,
                         args=(candidate, self.selected_track.path), daemon=True).start()

    def _lyrics_worker(self, candidate: Candidate, track_path: Path) -> None:
        try:
            duration = MP3(track_path).info.length
        except Exception:
            duration = None
        try:
            text, instrumental = self.catalog.lyrics_for(candidate, duration)
            self.events.put(("lyrics", (str(track_path), candidate, text, instrumental)))
        except Exception as exc:
            self.events.put(("lyrics_error", (str(track_path), candidate, str(exc))))

    def _get_cover(self) -> None:
        candidate = self.selected_candidate
        if not candidate:
            return
        self.cover_button.configure(state="disabled")
        self.status.set("Looking for high-resolution front-cover artwork…")
        threading.Thread(target=self._cover_worker,
                         args=(candidate, self.selected_track.path), daemon=True).start()

    def _cover_worker(self, candidate: Candidate, track_path: Path) -> None:
        try:
            data = self.catalog.cover_for(candidate)
            self.events.put(("cover", (str(track_path), candidate, data)))
        except Exception as exc:
            self.events.put(("cover_error", (str(track_path), candidate, str(exc))))

    def _apply(self) -> None:
        track, candidate = self.selected_track, self.selected_candidate
        if not track or not candidate:
            messagebox.showinfo(APP_NAME, "Select a song and a catalog match first.")
            return
        if candidate.score < 0.72:
            if not messagebox.askyesno(APP_NAME, "This match is uncertain. Apply it anyway?"):
                return
        if not messagebox.askyesno(APP_NAME,
                                   f"Save the confirmed details to:\n\n{track.path.name}\n\n"
                                   "The original will be backed up first."):
            return
        try:
            self._write_track(track, candidate)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not update the MP3:\n{exc}")
            return
        self.status.set(f"Updated {track.path.name}.")
        self._scan_folder()

    def _write_track(self, track: TrackFile, candidate: Candidate) -> None:
        backup_root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / APP_NAME / "Backups"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        relative = track.path.relative_to(Path(self.folder.get()))
        backup = backup_root / stamp / relative
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(track.path, backup)
        try:
            tags = ID3(track.path)
        except ID3NoHeaderError:
            tags = ID3()

        mapping = {
            "TIT2": (TIT2, candidate.title),
            "TPE1": (TPE1, candidate.artist),
            "TPE2": (TPE2, candidate.album_artist or candidate.artist),
            "TALB": (TALB, candidate.album),
            "TCON": (TCON, candidate.genre),
            "TCOM": (TCOM, candidate.composer),
            "TRCK": (TRCK, candidate.track_number),
        }
        current = tags
        for frame_id, (frame_type, value) in mapping.items():
            value = clean(value)
            if not value:
                continue
            if self.fill_empty.get() and frame_text(current, frame_id):
                continue
            tags.setall(frame_id, [frame_type(encoding=3, text=value)])
        if candidate.year and (not self.fill_empty.get() or not frame_text(current, "TDRC")):
            tags.setall("TDRC", [TDRC(encoding=3, text=candidate.year)])
        if candidate.release_date and (not self.fill_empty.get() or not frame_text(current, "TDRL")):
            tags.setall("TDRL", [TDRL(encoding=3, text=candidate.release_date)])

        artwork = self.cover_bytes
        # Artwork frames are keyed "APIC:<description>", so look them up with getall().
        preserve_existing_art = self.fill_empty.get() and bool(current.getall("APIC"))
        if artwork:
            with Image.open(io.BytesIO(artwork)) as image:
                image.load()
                output = io.BytesIO()
                mime = "image/png" if image.format == "PNG" else "image/jpeg"
                image.convert("RGB").save(output, format="PNG" if mime == "image/png" else "JPEG", quality=95)
                if not preserve_existing_art:
                    tags.setall("APIC", [APIC(encoding=3, mime=mime, type=3, desc="Front cover", data=output.getvalue())])
                if self.save_png.get():
                    art_dir = Path(self.folder.get()) / "Album Art"
                    art_dir.mkdir(exist_ok=True)
                    base = clean(f"{candidate.album_artist or candidate.artist} - {candidate.album or candidate.title}")
                    safe = re.sub(r'[<>:"/\\|?*]+', "_", base).strip(" .") or "cover"
                    output_path = art_dir / f"{safe}.png"
                    suffix = 2
                    while output_path.exists():
                        output_path = art_dir / f"{safe} ({suffix}).png"
                        suffix += 1
                    with Image.open(io.BytesIO(artwork)) as source:
                        source.convert("RGB").save(output_path, format="PNG")
        # Lyrics are written only when fetched for this match (like artwork). With "Only fill
        # blank fields" on, existing lyrics are kept.
        if self.lyrics_text:
            has_lyrics = any(str(frame.text).strip() for frame in current.getall("USLT"))
            if not (self.fill_empty.get() and has_lyrics):
                tags.setall("USLT", [USLT(encoding=3, lang="eng", desc="", text=self.lyrics_text)])
        tags.save(track.path, v2_version=4)

    def _show_details(self, text: str) -> None:
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("1.0", text)
        self.details.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "search":
                    track_path, result, errors = value
                    if not self.selected_track or str(self.selected_track.path) != track_path:
                        continue
                    self.candidates = result
                    self.match_list.delete(0, "end")
                    for item in self.candidates:
                        self.match_list.insert("end", item.display())
                    if self.candidates:
                        self.match_list.selection_set(0)
                        self._on_candidate_selected()
                        self.status.set(f"Found {len(self.candidates)} candidate matches. Review before applying.")
                    else:
                        if errors:
                            self.status.set("Catalog lookup failed: " + " | ".join(errors))
                        else:
                            self.status.set("No catalog matches found. Check the tags or try a clearer title.")
                    self.search_button.configure(state="normal")
                elif kind == "cover":
                    track_path, candidate, cover = value
                    if (not self.selected_track or str(self.selected_track.path) != track_path
                            or self.selected_candidate is not candidate):
                        continue
                    self.cover_bytes = cover
                    image = Image.open(io.BytesIO(cover))
                    # Preview only (the full-size cover_bytes are what get saved): fit the preview well.
                    image.thumbnail((min(260, max(90, self.cover_label.winfo_width() - 8)),
                                     min(220, max(90, self.cover_label.winfo_height() - 8))))
                    self.cover_preview = ImageTk.PhotoImage(image)
                    self.cover_label.configure(image=self.cover_preview, text="")
                    self.cover_button.configure(state="normal")
                    self.status.set("High-resolution cover found. Confirm the match, then apply.")
                elif kind == "cover_error":
                    track_path, candidate, error = value
                    if (not self.selected_track or str(self.selected_track.path) != track_path
                            or self.selected_candidate is not candidate):
                        continue
                    self.cover_button.configure(state="normal")
                    self.status.set(error)
                    messagebox.showinfo(APP_NAME, error)
                elif kind in ("lyrics", "lyrics_error"):
                    track_path, candidate = value[0], value[1]
                    if (not self.selected_track or str(self.selected_track.path) != track_path
                            or self.selected_candidate is not candidate):
                        continue
                    self.lyrics_button.configure(state="normal")
                    if kind == "lyrics_error":
                        self.status.set(f"Lyrics: {value[2]}")
                        self.view.show_lyrics(None, value[2])
                    elif value[3]:  # instrumental
                        self.status.set("This track is listed as instrumental, so it has no lyrics.")
                        self.view.show_lyrics(None, "This track is listed as instrumental.")
                    else:
                        self.lyrics_text = value[2]
                        self.view.show_lyrics(value[2])
                        self.status.set("Lyrics found. They will be saved into the MP3 when you apply.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)


def main() -> None:
    enable_dpi_awareness()
    register_fonts()
    root = tk.Tk()
    TrackAndCoverApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
