# No music yet? Three ways to fill your library

The Boo0om home server plays whatever is in your `music` folder. If that folder is empty, here is how to fill it. Whichever way you choose, put the files in folders like `Artist/Album/01 Song.mp3` and the server shows them within 15 minutes (or right away after a restart).

Services and their terms change. Everything below was checked in November 2026; read the service's own page before you rely on it.

## 1. Music you already own

- Songs you bought as downloads (Bandcamp, Qobuz, the iTunes Store, and so on) are ordinary files: copy them in.
- CDs can be copied to files with the Music app on a Mac or Windows Media Player on Windows.
- Songs from a streaming subscription (Spotify, Apple Music) are not files you own and can't be used.

## 2. Free music you are allowed to keep

Some artists and archives give music away for anyone to download and keep. Look for the words **public domain** or **CC0** next to the track; those need no credit and have no conditions. **CC BY** music is also free to keep, as long as you credit the artist if you share it.

- [Free Music Archive](https://freemusicarchive.org): filter by licence
- [Musopen](https://musopen.org): classical recordings
- [Internet Archive audio](https://archive.org/details/audio): live concerts and netlabels
- [Wikimedia Commons](https://commons.wikimedia.org/wiki/Category:Audio_files_of_music): each file shows its licence

Check the licence on each track rather than on the site as a whole.

## 3. Make your own with AI

### On your own computer, free: ACE-Step

[ACE-Step 1.5](https://github.com/ACE-Step/ACE-Step-1.5) is an open-source music generator (MIT licence) that runs on your own computer, so nothing is uploaded and there is no account or monthly limit. You describe the music you want, optionally with lyrics, and it writes a song.

What you need, from its install guide: about 10 GB of free disk space, and either a Mac with Apple silicon (M1 or later) or a PC with a graphics card with at least 4 GB of memory. It also runs without one, slowly.

The simple way:

1. Open the project's [install guide](https://github.com/ACE-Step/ACE-Step-1.5/blob/main/docs/en/INSTALL.md).
2. Download the **portable package** for Windows or macOS that the guide links to, unzip it, and start it with the script inside.
3. A page opens in your browser at `http://localhost:7860`. Type a description such as "warm lo-fi hip hop, mellow piano, 80 bpm" and press generate. The first start downloads the models, which takes a while.
4. Save the songs you like into your Boo0om `music` folder, for example `music/My AI Songs/Lo-fi/01 Rainy Window.mp3`.

If you are comfortable with a terminal, the guide's quick start is three commands:

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh      # installs the uv package manager (macOS, Linux)
git clone https://github.com/ACE-Step/ACE-Step-1.5.git && cd ACE-Step-1.5 && uv sync
uv run acestep                                       # opens http://localhost:7860
```

We have not tested ACE-Step ourselves; these steps come from its own documentation.

### In your browser: free plans of online services

Online generators such as [Suno](https://suno.com) and [Udio](https://www.udio.com) make songs in your browser with nothing to install, and have free plans with a daily allowance. Two things to know:

- **Free plans are for personal, non-commercial listening.** On Suno's free plan, Suno keeps ownership of the songs and lets you use them non-commercially; you may not sell them or earn money from them. Playing them at home in Boo0om is the kind of use that plan is for. Paid plans come with commercial rights.
- **Download the song as a file** (MP3 or WAV) from the service, then put it in your `music` folder like any other song.

Read the service's current terms before using its songs for anything public.

## Formats the server plays

MP3, M4A/AAC, FLAC, WAV and AIFF. Ogg and Opus files are skipped because iPhone and iPad can't play them; convert those to MP3 or M4A first (the free app [Audacity](https://www.audacityteam.org) can).

## Tips

- Name files with a track number first (`01 Song.mp3`) to keep an album in order.
- Put a picture called `cover.jpg` in an album's folder to give it a cover.
- A song with no tags takes its artist and album from the folder names, so `Artist/Album/` is all the organising you need.
