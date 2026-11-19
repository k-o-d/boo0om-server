# Boo0om home server

Play your own music collection in the **Boo0om** app, streamed from a computer in your house to your phone over your Wi-Fi. Nothing is uploaded anywhere: the music stays on your computer and only devices on your home network can reach it.

You need:

- a computer that stays on while you listen (Mac, Windows or Linux; a Raspberry Pi or a NAS works too)
- a folder of music files (MP3, M4A/AAC, FLAC, WAV or AIFF)
- your phone on the same Wi-Fi as that computer

## Set it up in five steps

**1. Install Python** (free, one time). Get it from [python.org/downloads](https://www.python.org/downloads/) and run the installer. On Windows, tick **Add python.exe to PATH** on the installer's first screen.

**2. Download this server.** On this page press the green **Code** button, then **Download ZIP**. Open the ZIP and move the folder somewhere you'll find it again, such as Documents.

**3. Add your music.** Copy your music into the `music` folder inside the folder you just downloaded. Folders inside it are fine. If your music already lives somewhere else, leave it there and write that folder's location into `music-folder.txt` instead (the file explains how).

**4. Start the server.**

- **Mac:** double-click `Start Boo0om Server (Mac).command`. The first time, macOS may say it can't be opened because it is from the internet: right-click the file, choose **Open**, then **Open** again.
- **Windows:** double-click `Start Boo0om Server (Windows).bat`. If Windows shows "Windows protected your PC", press **More info**, then **Run anyway**. If it asks about the firewall, allow it on **private** networks.

The first start takes about a minute. Then a page opens in your browser that says **Running** and shows an address like `http://192.168.1.20:9813`.

**5. Connect the app.** Open Boo0om on your phone. On the welcome screen, or later under **Settings → Server**, type the address from that page and press **Test & Continue**. Your library appears.

To stop the server, close its window. To start it again, double-click the same file.

No music yet? The first start adds three short demo tracks, so you can check that everything works before copying your own music in. Delete the `Boo0om Demo` folder inside `music` whenever you like.

## If something doesn't work

| What you see | What to try |
|---|---|
| The app says it can't reach the server | Check the phone is on the same Wi-Fi as the computer (not mobile data, not a guest network). Type the address exactly as the page shows it, starting with `http://` and ending with `:9813`. |
| It worked yesterday and not today | The computer's address can change. Open `http://localhost:9813` on the computer to see the current one. Your router can give the computer a fixed address ("DHCP reservation") so it stops changing. |
| It stops when the computer sleeps | Turn off sleep while you listen, or use a computer that stays on. |
| New songs don't show up | The server looks for new files every 15 minutes. Restart it to see them at once. |
| Songs show as "Unknown Artist" | The files have no tags. Either tag them with a music tagger, or arrange them as `Artist/Album/01 Song.mp3` and the server reads the names from the folders. |
| No album covers | Put a picture named `cover.jpg` in the album's folder. Covers stored inside the music files are found too. |
| Windows never asked about the firewall | Open Windows Security → Firewall → Allow an app, and allow Python on private networks. |

## How your music is read

- Song, artist, album, track number and year come from each file's tags. Without tags, the folder names are used: `Artist/Album/01 Song.mp3`.
- Covers come from `cover.jpg` (also `folder`, `front`, `album`, `artwork`; `.jpg`, `.png` or `.webp`) in the album's folder, else from the picture inside the music file.
- Lyrics come from a text file next to the song with the same name: `Song.lrc` for lyrics that follow the music, `Song.txt` for plain lyrics.
- The music folder is only ever read. The server writes to the `data` folder beside it: resized covers, and the list that lets a second device fetch what the first one downloaded.

## Keep it at home

This server has **no password**. It is meant for your home network, where only your own devices can reach it. Don't open its port on your router or put it on the public internet. To listen away from home, use a private network such as [Tailscale](https://tailscale.com) or your router's VPN, and type the computer's address on that network into the app.

## For people comfortable with a terminal

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
MUSIC_DIR=/path/to/music .venv/bin/python server.py
```

Or with Docker (edit the music path in `compose.yaml` first):

```sh
docker compose up -d
```

Settings are environment variables, all optional:

| Variable | Default | What it does |
|---|---|---|
| `MUSIC_DIR` | the folder in `music-folder.txt`, else `./music` | where the music is |
| `DATA_DIR` | `./data` | where covers and the downloads list are kept |
| `HOST` | `0.0.0.0` | address to listen on |
| `PORT` | `9813` | port to listen on |
| `RESCAN_MINUTES` | `15` | how often to look for new files; `0` turns it off |
| `DEMO` | off (the double-click starters turn it on) | `1` writes three synthesized demo tracks when the music folder is empty |
| `OPEN_BROWSER` | off (the double-click starters turn it on) | `1` opens the status page at start |

The app talks to `/api/v1/...`; `http://localhost:9813/docs` lists every address the server answers. The whole server is one file, `server.py`.

## Licence

MIT. See [LICENSE](LICENSE).
