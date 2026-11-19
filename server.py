"""
Boo0om home server.

Serves a folder of music to the Boo0om app over your own network. It scans the
folder, reads the tags, and answers the API the app calls (/api/v1/...):
artists, albums, tracks, search, cover art, lyrics, streaming and the
downloads list. Everything is kept in memory; there is no database.

Settings (environment variables, all optional):

    MUSIC_DIR       folder with your music            (default: the folder
                    named in music-folder.txt, else ./music)
    DATA_DIR        folder this server may write to   (default ./data)
    HOST            address to listen on              (default 0.0.0.0)
    PORT            port to listen on                 (default 9813)
    RESCAN_MINUTES  look for new files this often     (default 15, 0 = never)
    DEMO            1 = if MUSIC_DIR has no music, write three short
                    synthesized tracks into it so there is something to play
    OPEN_BROWSER    1 = open the status page in your browser at start
    READ_ONLY       1 = public demo mode: the downloads list is switched off
                    and the status page hides this computer's details
    PUBLIC_URL      the address to show on the status page in that mode

Run it with:  python server.py
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import math
import os
import random
import re
import struct
import threading
import time
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import mutagen
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, Response
from PIL import Image
from pydantic import BaseModel, Field

HERE = Path(__file__).resolve().parent


def music_folder() -> Path:
    """MUSIC_DIR, else the folder written in music-folder.txt, else ./music."""
    chosen = os.environ.get("MUSIC_DIR", "").strip()
    note = HERE / "music-folder.txt"
    if not chosen and note.is_file():
        lines = [line.strip().strip('"') for line in note.read_text(encoding="utf-8", errors="replace").splitlines()]
        chosen = next((line for line in lines if line and not line.startswith("#")), "")
    return Path(chosen or HERE / "music").expanduser().resolve()


MUSIC_DIR = music_folder()
DATA_DIR = Path(os.environ.get("DATA_DIR", "") or HERE / "data").expanduser().resolve()
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "9813"))
RESCAN_MINUTES = float(os.environ.get("RESCAN_MINUTES", "15"))
DEMO = os.environ.get("DEMO", "").lower() in ("1", "true", "yes")
OPEN_BROWSER = os.environ.get("OPEN_BROWSER", "").lower() in ("1", "true", "yes")
# For a server that anyone on the internet can reach (a demo library): nothing
# a visitor sends is stored, and the status page shows PUBLIC_URL instead of
# this computer's address and folder.
READ_ONLY = os.environ.get("READ_ONLY", "").lower() in ("1", "true", "yes")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")

# Formats the app's player (AVPlayer on iOS) can play.
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".flac": "audio/flac",
    ".wav": "audio/wav",
    ".aif": "audio/aiff",
    ".aiff": "audio/aiff",
    ".caf": "audio/x-caf",
}
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
COVER_NAMES = ("cover", "folder", "front", "album", "artwork")
COVER_SIZES = (128, 256, 512, 1024)
UNKNOWN_ARTIST = "Unknown Artist"
UNKNOWN_ALBUM = "Unknown Album"


# =============================================================================
# The library
# =============================================================================

@dataclass
class Track:
    id: str
    path: Path
    title: str
    artist: str
    album_artist: str
    album: str
    duration: float
    number: Optional[int]
    year: Optional[int]
    album_id: str = ""


@dataclass
class Album:
    id: str
    name: str
    artist: str
    artist_id: str
    year: Optional[int] = None
    tracks: List[Track] = field(default_factory=list)
    has_cover: bool = False


@dataclass
class Artist:
    id: str
    name: str
    albums: List[Album] = field(default_factory=list)


@dataclass
class Library:
    tracks: Dict[str, Track] = field(default_factory=dict)
    albums: Dict[str, Album] = field(default_factory=dict)
    artists: Dict[str, Artist] = field(default_factory=dict)
    scanned_at: float = 0.0


library = Library()
_scan_lock = threading.Lock()


def make_id(*parts: str) -> str:
    """A stable 24-character id, so ids survive a restart and a rescan."""
    return hashlib.sha1("\x1f".join(parts).encode("utf-8")).hexdigest()[:24]


def sort_key(name: str) -> str:
    key = name.strip().lower()
    return key[4:] if key.startswith("the ") else key


def first_tag(tags, name: str) -> Optional[str]:
    try:
        value = tags.get(name) if tags else None
    except Exception:
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    text = str(value).strip() if value is not None else ""
    return text or None


def leading_int(text: Optional[str]) -> Optional[int]:
    match = re.match(r"\s*(\d+)", text or "")
    return int(match.group(1)) if match else None


def read_track(path: Path) -> Optional[Track]:
    """Reads one file's tags. Missing tags fall back to the folder layout
    Artist/Album/01 Title.ext; a file that can't be read at all is skipped."""
    relative = path.relative_to(MUSIC_DIR)
    tags, duration = None, 0.0
    try:
        audio = mutagen.File(path, easy=True)
        if audio is not None:
            tags = audio.tags
            duration = float(getattr(audio.info, "length", 0.0) or 0.0)
    except Exception:
        pass
    if duration <= 0 and path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as wav:
                duration = wav.getnframes() / float(wav.getframerate() or 1)
        except Exception:
            pass

    folders = relative.parts[:-1]
    stem = path.stem
    number = leading_int(first_tag(tags, "tracknumber"))
    title = first_tag(tags, "title")
    if not title:
        match = re.match(r"^\s*(\d{1,3})[\s._-]+(.+)$", stem)
        if match:
            number = number or int(match.group(1))
            title = match.group(2).strip()
        else:
            title = stem
    album = first_tag(tags, "album") or (folders[-1] if folders else UNKNOWN_ALBUM)
    artist = first_tag(tags, "artist") or (folders[-2] if len(folders) >= 2 else UNKNOWN_ARTIST)
    album_artist = first_tag(tags, "albumartist") or artist
    year = leading_int(first_tag(tags, "date") or first_tag(tags, "year"))

    return Track(
        id=make_id("track", relative.as_posix()),
        path=path,
        title=title,
        artist=artist,
        album_artist=album_artist,
        album=album,
        duration=round(duration, 3),
        number=number,
        year=year if year and 1000 <= year <= 9999 else None,
    )


def folder_cover(folder: Path) -> Optional[Path]:
    """cover.jpg, folder.png and the like; else any one image in the folder."""
    try:
        images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS and p.is_file())
    except OSError:
        return None
    for name in COVER_NAMES:
        for image in images:
            if image.stem.lower() == name:
                return image
    return images[0] if images else None


def embedded_cover(path: Path) -> Optional[bytes]:
    """The picture stored inside an audio file (ID3, MP4 or FLAC), if any."""
    try:
        audio = mutagen.File(path)
    except Exception:
        return None
    if audio is None:
        return None
    pictures = getattr(audio, "pictures", None)
    if pictures:
        return bytes(pictures[0].data)
    tags = audio.tags
    if tags is None:
        return None
    try:
        for key in tags.keys():
            if key.startswith("APIC"):
                return bytes(tags[key].data)
        covers = tags.get("covr")
        if covers:
            return bytes(covers[0])
    except Exception:
        return None
    return None


def album_cover_bytes(album: Album) -> Optional[bytes]:
    for track in album.tracks:
        image = folder_cover(track.path.parent)
        if image:
            try:
                return image.read_bytes()
            except OSError:
                pass
        break
    for track in album.tracks[:3]:
        data = embedded_cover(track.path)
        if data:
            return data
    return None


def scan() -> Library:
    """Walks MUSIC_DIR and builds a fresh library."""
    new = Library(scanned_at=time.time())
    if MUSIC_DIR.is_dir():
        for root, dirs, files in os.walk(MUSIC_DIR, followlinks=True):
            dirs[:] = sorted(d for d in dirs if not d.startswith("."))
            for name in sorted(files):
                if name.startswith(".") or Path(name).suffix.lower() not in AUDIO_TYPES:
                    continue
                track = read_track(Path(root) / name)
                if track is None:
                    continue
                artist_id = make_id("artist", sort_key(track.album_artist))
                album_id = make_id("album", sort_key(track.album_artist), track.album.strip().lower())
                track.album_id = album_id
                artist = new.artists.setdefault(artist_id, Artist(id=artist_id, name=track.album_artist))
                album = new.albums.get(album_id)
                if album is None:
                    album = Album(id=album_id, name=track.album, artist=track.album_artist, artist_id=artist_id)
                    new.albums[album_id] = album
                    artist.albums.append(album)
                album.tracks.append(track)
                album.year = album.year or track.year
                new.tracks[track.id] = track

    for album in new.albums.values():
        album.tracks.sort(key=lambda t: (t.number or 0, t.title.lower()))
        album.has_cover = album_cover_bytes(album) is not None
    for artist in new.artists.values():
        artist.albums.sort(key=lambda a: (a.year or 0, a.name.lower()))
    return new


def rescan() -> None:
    global library
    with _scan_lock:
        fresh = scan()
        library = fresh
    print(f"Library: {len(fresh.tracks)} tracks, {len(fresh.albums)} albums, "
          f"{len(fresh.artists)} artists in {MUSIC_DIR}", flush=True)


def rescan_forever() -> None:
    while RESCAN_MINUTES > 0:
        time.sleep(RESCAN_MINUTES * 60)
        try:
            rescan()
        except Exception as error:  # keep serving the previous library
            print(f"Rescan failed: {error}", flush=True)


# =============================================================================
# Demo tracks (DEMO=1): short synthesized tunes, so nothing is borrowed
# =============================================================================

def write_demo_tracks() -> None:
    folder = MUSIC_DIR / "Boo0om Demo" / "First Signals"
    folder.mkdir(parents=True, exist_ok=True)
    rate = 22050
    tunes = [
        ("01 Rising", [262, 330, 392, 523, 392, 330, 262, 330]),
        ("02 Night Bus", [220, 262, 220, 196, 175, 196, 220, 262]),
        ("03 Open Window", [294, 370, 440, 370, 294, 247, 294, 370]),
    ]
    for name, notes in tunes:
        frames = bytearray()
        for _ in range(5):
            for note in notes:
                count = int(rate * 0.5)
                for i in range(count):
                    fade = min(1.0, i / 400, (count - i) / 2000)
                    sample = math.sin(2 * math.pi * note * i / rate) + 0.3 * math.sin(4 * math.pi * note * i / rate)
                    frames += struct.pack("<h", int(sample * fade * 9000))
        with wave.open(str(folder / f"{name}.wav"), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))

    cover = Image.new("RGB", (600, 600))
    pixels = cover.load()
    for y in range(600):
        for x in range(600):
            pixels[x, y] = (250 - y // 4, 60 + x // 8, 80 + (x + y) // 10)
    cover.save(folder / "cover.jpg", quality=85)


def has_music() -> bool:
    if not MUSIC_DIR.is_dir():
        return False
    return any(Path(name).suffix.lower() in AUDIO_TYPES
               for _, _, files in os.walk(MUSIC_DIR, followlinks=True) for name in files)


# =============================================================================
# What the app receives
# =============================================================================

def image_urls(album: Optional[Album]) -> Optional[dict]:
    if album is None or not album.has_cover:
        return None
    name = f"{album.id}.jpg"
    urls = {label: f"/api/v1/cover/{name}?size={size}"
            for label, size in zip(("small", "medium", "large", "xl"), COVER_SIZES)}
    urls["original"] = f"/api/v1/cover/{name}"
    return urls


def track_json(track: Track) -> dict:
    return {
        "title": track.title,
        "artist": track.artist,
        "album": track.album,
        "duration": track.duration,
        "trackNumber": track.number,
        "streamUrl": f"/api/v1/stream/{track.id}",
        "images": image_urls(library.albums.get(track.album_id)),
    }


def album_json(album: Album) -> dict:
    return {
        "id": album.id,
        "name": album.name,
        "artist": album.artist,
        "year": album.year,
        "trackCount": len(album.tracks),
        "images": image_urls(album),
    }


def artist_json(artist: Artist) -> dict:
    with_cover = next((album for album in artist.albums if album.has_cover), None)
    return {
        "id": artist.id,
        "name": artist.name,
        "albumCount": len(artist.albums),
        "trackCount": sum(len(album.tracks) for album in artist.albums),
        "images": image_urls(with_cover),
    }


def paged(items: list, page: int, limit: int) -> dict:
    total = len(items)
    start = (page - 1) * limit
    return {
        "data": items[start:start + limit],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "totalPages": math.ceil(total / limit) if total else 0,
        },
    }


def in_range(name: str, letters: Optional[str]) -> bool:
    """range=AC keeps names starting with A to C; the first range also takes
    digits and symbols, and range=09 is digits only."""
    if not letters:
        return True
    first = sort_key(name)[:1].upper()
    start, end = letters[0], letters[1]
    if start.isdigit():
        return first.isdigit()
    if start == "A" and not first.isalpha():
        return True
    return start <= first <= end


def matches(query: str, *values: str) -> bool:
    needle = query.strip().lower()
    return any(needle in (value or "").lower() for value in values)


@asynccontextmanager
async def lifespan(_: FastAPI):
    start()
    yield


app = FastAPI(title="Boo0om home server", version="1.0.0", docs_url="/docs", redoc_url=None, lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def home():
    """The status page: is it running, how much music, what to type in the app."""
    address = None if READ_ONLY else lan_address()
    url = PUBLIC_URL or (f"http://{address}:{PORT}" if address else None)
    empty = not library.tracks
    folder_line = "" if READ_ONLY else f'<div class="small">Music folder: <code>{html.escape(str(MUSIC_DIR))}</code></div>'
    network_line = ("This is a public demo library. Anyone can listen; nothing you do is stored."
                    if READ_ONLY else "Your phone has to be on the same Wi-Fi as this computer.")
    closing_line = ("" if READ_ONLY else
                    '{closing_line}')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Boo0om home server</title>
<style>
  body {{ font: 17px/1.5 -apple-system, "Segoe UI", sans-serif; background: #121217; color: #f2f2f2;
         max-width: 34em; margin: 0 auto; padding: 2em 1em; }}
  h1 {{ font-size: 1.5em; margin: 0 0 .2em; }}
  .ok {{ color: #6fd08c; }} .warn {{ color: #ffb454; }}
  .box {{ background: #1f1f25; border-radius: 12px; padding: 1em 1.2em; margin: 1em 0; }}
  .address {{ font: 600 1.35em ui-monospace, Menlo, Consolas, monospace; color: #fa5252; word-break: break-all;
              user-select: all; }}
  .small {{ color: #9a9aa2; font-size: .9em; }}
  code {{ word-break: break-all; }}
</style></head><body>
<h1>Boo0om home server</h1>
<p class="ok">● Running</p>
<div class="box">
  <div class="small">Type this into the Boo0om app, under Settings → Server</div>
  <div class="address">{html.escape(url) if url else "this computer's network address, then :" + str(PORT)}</div>
  <div class="small">{network_line}</div>
</div>
<div class="box">
  <strong>{len(library.tracks)}</strong> songs · <strong>{len(library.albums)}</strong> albums ·
  <strong>{len(library.artists)}</strong> artists
  {folder_line}
  {'<p class="warn">No music found yet. Copy some songs into that folder; they show up within '
   + str(int(RESCAN_MINUTES) or 15) + ' minutes, or right away if you restart the server.</p>' if empty else ''}
</div>
<p class="small">Keep this computer on and awake while you listen. To stop the server, close its window.</p>
</body></html>"""


@app.get("/api/v1/health")
def health():
    return {"api": "healthy", "database": "healthy", "fileServer": "healthy"}


@app.get("/api/v1/stats")
def stats():
    return {
        "totalSongs": len(library.tracks),
        "totalAlbums": len(library.albums),
        "totalArtists": len(library.artists),
    }


@app.get("/api/v1/discover")
def discover(count: int = Query(50, ge=1, le=200)):
    tracks = list(library.tracks.values())
    picked = random.sample(tracks, min(count, len(tracks)))
    return {"data": [track_json(track) for track in picked], "count": len(picked)}


@app.get("/api/v1/artists")
def list_artists(
    range: Optional[str] = Query(None, pattern=r"^[0-9A-Z]{2}$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    artists = sorted((a for a in library.artists.values() if in_range(a.name, range)), key=lambda a: sort_key(a.name))
    return paged([artist_json(artist) for artist in artists], page, limit)


@app.get("/api/v1/artist/{artist_id}")
def get_artist(artist_id: str):
    artist = library.artists.get(artist_id)
    if artist is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return {
        **artist_json(artist),
        "artistArt": None,
        "albums": [album_json(album) for album in artist.albums],
        "singles": [],
        "tracks": [track_json(track) for album in artist.albums for track in album.tracks],
    }


@app.get("/api/v1/albums")
def list_albums(
    range: Optional[str] = Query(None, pattern=r"^[0-9A-Z]{2}$"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    min_tracks: int = Query(1, ge=1),
):
    albums = sorted(
        (a for a in library.albums.values() if in_range(a.name, range) and len(a.tracks) >= min_tracks),
        key=lambda a: sort_key(a.name),
    )
    return paged([album_json(album) for album in albums], page, limit)


@app.get("/api/v1/album/{album_id}")
def get_album(album_id: str):
    album = library.albums.get(album_id)
    if album is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return {**album_json(album), "tracks": [track_json(track) for track in album.tracks]}


@app.get("/api/v1/track/{track_id}")
def get_track(track_id: str):
    track = library.tracks.get(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")
    return track_json(track)


def found_artists(q: str) -> List[Artist]:
    return sorted((a for a in library.artists.values() if matches(q, a.name)), key=lambda a: sort_key(a.name))


def found_albums(q: str) -> List[Album]:
    return sorted((a for a in library.albums.values() if matches(q, a.name, a.artist)), key=lambda a: sort_key(a.name))


def found_tracks(q: str) -> List[Track]:
    return sorted((t for t in library.tracks.values() if matches(q, t.title, t.artist, t.album)),
                  key=lambda t: t.title.lower())


@app.get("/api/v1/search")
def search(
    q: str = Query(..., min_length=1),
    type: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    kind = (type or "all").lower()
    start = (page - 1) * limit
    result = {"query": q, "artists": [], "albums": [], "tracks": [], "pagination": {"page": page, "limit": limit}}
    if kind in ("all", "artist", "artists"):
        artists = found_artists(q)
        result["artists"] = [artist_json(a) for a in artists[start:start + limit]]
        result["artistTotal"] = len(artists)
    if kind in ("all", "album", "albums"):
        albums = found_albums(q)
        result["albums"] = [album_json(a) for a in albums[start:start + limit]]
        result["albumTotal"] = len(albums)
    if kind in ("all", "track", "tracks"):
        tracks = found_tracks(q)
        result["tracks"] = [track_json(t) for t in tracks[start:start + limit]]
        result["trackTotal"] = len(tracks)
    return result


@app.get("/api/v1/search/artists")
def search_artists(q: str = Query(..., min_length=1), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    return paged([artist_json(a) for a in found_artists(q)], page, limit)


@app.get("/api/v1/search/albums")
def search_albums(q: str = Query(..., min_length=1), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    return paged([album_json(a) for a in found_albums(q)], page, limit)


@app.get("/api/v1/search/tracks")
def search_tracks(q: str = Query(..., min_length=1), page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100)):
    return paged([track_json(t) for t in found_tracks(q)], page, limit)


# =============================================================================
# Streaming, cover art, lyrics
# =============================================================================

@app.get("/api/v1/stream/{track_id}")
def stream(track_id: str):
    """The audio file itself. Range requests (seeking) are answered by FileResponse."""
    track = library.tracks.get(track_id)
    if track is None or not track.path.is_file():
        raise HTTPException(status_code=404, detail="Track not found")
    return FileResponse(track.path, media_type=AUDIO_TYPES.get(track.path.suffix.lower(), "application/octet-stream"))


@app.get("/api/v1/cover/{filename}")
def cover(filename: str, size: Optional[int] = None):
    """An album's cover as a square JPEG, at 128, 256, 512 or 1024 pixels, or
    at most 1600 without a size. Resized covers are kept in DATA_DIR/covers."""
    album = library.albums.get(Path(filename).stem)
    if album is None or not album.has_cover:
        raise HTTPException(status_code=404, detail="Cover not found")
    side = min(COVER_SIZES, key=lambda s: abs(s - size)) if size else 1600

    cache = DATA_DIR / "covers" / f"{album.id}-{side}.jpg"
    newest = max((track.path.stat().st_mtime for track in album.tracks[:1] if track.path.exists()), default=0)
    if cache.is_file() and cache.stat().st_mtime >= newest:
        return FileResponse(cache, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

    data = album_cover_bytes(album)
    if data is None:
        raise HTTPException(status_code=404, detail="Cover not found")
    try:
        image = Image.open(io.BytesIO(data)).convert("RGB")
        image.thumbnail((side, side))
        out = io.BytesIO()
        image.save(out, "JPEG", quality=85)
    except Exception:
        raise HTTPException(status_code=404, detail="Cover could not be read")
    try:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(out.getvalue())
    except OSError:
        pass  # a read-only DATA_DIR only costs the cache
    return Response(out.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/v1/artist-art/{filename}")
def artist_art(filename: str):
    raise HTTPException(status_code=404, detail="This server has no separate artist pictures")


LRC_TIME_TAG = re.compile(r"\[(\d{1,3}):([0-5]\d)(?:\.(\d{1,3}))?\]")


def parse_lrc(content: str) -> List[dict]:
    """Timed lines of an .lrc file, sorted; each line ends where the next starts."""
    entries = []
    for raw in content.splitlines():
        line = raw.strip()
        times, position = [], 0
        while True:
            match = LRC_TIME_TAG.match(line, position)
            if not match:
                break
            minutes, seconds, fraction = match.groups()
            times.append(round(int(minutes) * 60 + int(seconds) + (float(f"0.{fraction}") if fraction else 0.0), 3))
            position = match.end()
        text = line[position:].strip()
        entries.extend((start, text) for start in times)
    entries.sort(key=lambda entry: entry[0])

    lines = []
    for index, (start, text) in enumerate(entries):
        if not text:
            continue
        end = next((later for later, _ in entries[index + 1:] if later > start), None)
        lines.append({"start_time": start, "end_time": end, "text": text})
    return lines


@app.get("/api/v1/lyrics/{track_id}")
def lyrics(track_id: str):
    """Lyrics from a file next to the audio: "<name>.lrc" (timed) or "<name>.txt"."""
    track = library.tracks.get(track_id)
    if track is None:
        raise HTTPException(status_code=404, detail="Track not found")
    timed = track.path.with_suffix(".lrc")
    plain = track.path.with_suffix(".txt")
    if timed.is_file():
        lines = parse_lrc(timed.read_text(encoding="utf-8", errors="replace"))
        if lines:
            return {"track_hash": track_id, "is_synced": True, "lines": lines, "plain_text": None}
    if plain.is_file():
        text = "\n".join(line.strip() for line in plain.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())
        if text:
            return {"track_hash": track_id, "is_synced": False, "lines": None, "plain_text": text}
    raise HTTPException(status_code=404, detail="No lyrics for this track")


# =============================================================================
# Downloads list: lets a second device fetch what the first one downloaded
# =============================================================================

USERNAME = re.compile(r"^[a-z0-9_.-]{3,32}$")
MAX_SYNC_TRACKS = 50000
_sync_lock = threading.Lock()


class SyncTrack(BaseModel):
    id: str
    title: str
    artist: str
    album: str
    duration: float = 0
    trackNumber: Optional[int] = None
    streamHash: str
    images: Optional[dict] = None


class SyncRequest(BaseModel):
    username: str
    tracks: List[SyncTrack] = Field(default_factory=list)


def sync_file(raw_username: str) -> Path:
    username = (raw_username or "").strip().lower()
    if not USERNAME.match(username):
        raise HTTPException(status_code=400, detail="Username must be 3-32 chars: letters, digits, '.', '_', '-'")
    return DATA_DIR / "sync" / f"{username}.json"


@app.post("/api/v1/sync/downloads")
def save_downloads(payload: SyncRequest):
    """Adds a device's downloaded tracks to the user's list. Tracks are only
    ever added, so a new device can't empty another device's list."""
    if READ_ONLY:
        raise HTTPException(status_code=403, detail="This is a read-only demo library; the downloads list is switched off.")
    path = sync_file(payload.username)
    if len(payload.tracks) > MAX_SYNC_TRACKS:
        raise HTTPException(status_code=413, detail=f"Too many tracks in one push (max {MAX_SYNC_TRACKS})")
    now = int(time.time())
    with _sync_lock:
        saved = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        by_id = {track["id"]: track for track in saved.get("tracks", []) if track.get("id")}
        prior = len(by_id)
        added = duplicates = 0
        for track in payload.tracks:
            if not track.id:
                continue
            if track.id in by_id:
                duplicates += 1
            else:
                by_id[track.id] = track.model_dump()
                added += 1
        if len(by_id) > MAX_SYNC_TRACKS:
            raise HTTPException(status_code=413, detail=f"The list would exceed {MAX_SYNC_TRACKS} tracks")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({
            "username": path.stem,
            "tracks": list(by_id.values()),
            "updated_at": now,
            "created_at": saved.get("created_at", now),
        }), encoding="utf-8")
        temporary.replace(path)
    return {"username": path.stem, "trackCount": len(by_id), "added": added, "duplicates": duplicates,
            "priorCount": prior, "updatedAt": now}


@app.get("/api/v1/sync/downloads/{username}")
def get_downloads(username: str):
    path = sync_file(username)
    if READ_ONLY or not path.is_file():
        raise HTTPException(status_code=404, detail="No saved downloads for this username")
    saved = json.loads(path.read_text(encoding="utf-8"))
    tracks = saved.get("tracks", [])
    return {"username": path.stem, "tracks": tracks, "trackCount": len(tracks),
            "updatedAt": saved.get("updated_at"), "createdAt": saved.get("created_at")}


# =============================================================================
# Start
# =============================================================================

def lan_address() -> Optional[str]:
    import socket
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))  # no packet is sent; this only picks the outgoing interface
            return probe.getsockname()[0]
    except OSError:
        return None


def start() -> None:
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    if DEMO and not READ_ONLY and not has_music():
        print("DEMO=1 and no music found: writing three demo tracks.", flush=True)
        write_demo_tracks()
    rescan()
    threading.Thread(target=rescan_forever, daemon=True).start()
    address = lan_address()
    if address and not READ_ONLY and HOST in ("0.0.0.0", "::"):
        print(f"\nIn the Boo0om app, set the server to  http://{address}:{PORT}\n", flush=True)
    if OPEN_BROWSER:
        import webbrowser
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{PORT}/")).start()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
