# BeReal Exporter

Turns a BeReal data export into dated, geotagged image files you can drop into a photo library. It doesn't download anything from BeReal - you have to [request your data](https://www.reddit.com/r/bereal_app/comments/19dl0yk/experiencetutorial_for_exporting_all_bereal/) from them first.

Handles posts, memories, realmojis and conversation images, in parallel, with EXIF dates worked out from the GPS coordinates on each photo. (BeReal stores times like `"takenTime": "2024-12-24T01:27:16.726Z"` alongside a different `"berealMoment": "2024-12-23T22:39:05.327Z"`, so the real local time has to be reconstructed - see [Timezones](#timezones).)

## Installation

```sh
git clone https://github.com/ada-jm4122/BeReal-Export-Manager.git
cd BeReal-Export-Manager
pip install -r requirements.txt
```

Then install `exiftool` and make sure it's on your `PATH`. This is **required** - all metadata is written through it and the script fails immediately without it.

- Linux / WSL: `sudo apt install libimage-exiftool-perl`
- macOS: `brew install exiftool`
- Windows: [exiftool.org](https://exiftool.org/), or pass `--exiftool-path C:\path\to\exiftool.exe`

## Which BeReal download do I need?

BeReal may send you **two different files**. Only one is any use:

| File | What it is | Use it? |
|---|---|---|
| A large `.zip` (hundreds of MB+) named `<userid>-<random>.zip` | Your photos plus `posts.json` / `memories.json` / `realmojis.json` | **Yes** |
| A small `<userid>_<timestamp>.json.gz` (tens of KB) | Analytics - a log of `applicationOpened` events and city-level location history. No photos. | No |

If your download unzips to lines of `{"event_type":"applicationOpened",...}`, that's the telemetry file; the photo archive is a separate email.

## Setting up the input folder

The script scans **subfolders** of `input/`, and BeReal's zip has no wrapping folder of its own, so unzip it into one you create:

```sh
mkdir -p input/export
unzip -o your-bereal-export.zip -d input/export
```

You should end up with `input/export/` containing `memories.json`, `posts.json`, `realmojis.json`, `Photos/` and `conversations/`.

- **Don't unzip straight into `input/`** - only subdirectories are scanned, so you'd get `No BeReal export folder found in input directory`.
- **Use `unzip -o`** - the archive contains *two* files named `realmojis.json`, and without `-o` unzip stops to ask about the collision. With it, the larger correct one wins.

Keep only one export folder in `input/` at a time; with two, which one gets picked is arbitrary.

## Usage

```sh
python bereal_exporter.py              # everything, into ./output
python bereal_exporter.py --year 2024  # one year, good for a first test
```

A few thousand BeReals takes a while, so test on a year first. If a run is interrupted, just start it again - existing files are skipped, so it picks up where it left off. Pass `--overwrite` to force a redo.

### Options

- `-v, --verbose` - explain what is being done
- `-t, --timespan` - `DD.MM.YYYY-DD.MM.YYYY`, wildcards allowed (`DD.MM.YYYY-*`). Both dates read as midnight, so the end date is effectively **exclusive** - set it a day later than you think
- `-y, --year` - export a single year
- `-p, --out-path` - output folder (default `./output`)
- `--input-path` - folder *containing* your export folder (default `./input`)
- `--exiftool-path` - path to ExifTool if it isn't on `$PATH`
- `--max-workers` - parallel workers (default 4; try 8+ on a fast SSD)
- `--overwrite` - re-export images that already exist
- `--no-memories` / `--no-posts` / `--no-realmojis` / `--no-conversations` - skip a source
- `--conversations-only` - conversations only, for debugging
- `--interactive-conversations` - manually pick front/back camera for conversation images
- `--web-ui` - do that picking in a browser instead of the terminal

## What gets exported

```
output/
├── posts/                  every BeReal, 3 files each
├── realmojis/              your reaction selfies
└── conversations/<id>/     images sent in private conversations
```

**Every BeReal produces three files:**

- `2022-09-10_16-35-30_main-view.webp` - back camera
- `2022-09-10_16-35-30_selfie-view.webp` - front camera
- `2022-09-10_16-35-30_composited.webp` - the two combined, front overlaid on back with rounded corners, the way BeReal displayed it

So ~2,000 BeReals becomes ~6,000 files. Worth knowing before importing into a photo library, where all three show up as separate items - most people only want the `_composited` ones.

`posts.json` and `memories.json` are two descriptions of the *same* BeReals (memories carry the richer metadata). They're merged into one pass, so each image is only processed once. Conversation images are genuinely separate content - BeReals sent privately in chats - and don't duplicate anything in `posts/`.

Every image gets `DateTimeOriginal` / `CreateDate` set to the local time it was taken, plus GPS coordinates where BeReal recorded them. A small number of images referenced in the JSON are simply missing from BeReal's archive; those print `File not found in expected locations:` and are skipped.

## Splitting the output by view

`organize_output.py` sorts the three views into their own folders, so you can upload just the one you want:

```sh
python organize_output.py            # sorts ./output/posts
python organize_output.py --dry-run  # show what would move first
python organize_output.py --copy     # leave the originals in place
```

```
output/
├── main-view/     back camera
├── selfie-view/   front camera
└── composited/    the combined images - usually the only folder worth uploading
```

Point it elsewhere with `--source`, e.g. `--source output/conversations/<id>`.

## Stitching them into a video

`make_video.py` turns every composited BeReal into a single MP4, oldest first:

```sh
python make_video.py                          # -> output/bereals.mp4
python make_video.py --year 2024 --date-label # one year, date burned into each frame
python make_video.py --limit 100 -o test.mp4  # quick preview before committing to the lot
```

It reads `output/composited/` if you've run `organize_output.py`, otherwise the `_composited` files in `output/posts/`. Frames are ordered by the timestamp in the filename and normalized to one size (by default whichever size most of your images already are, so the bulk pass through untouched). Any video BeReals in the folder are skipped - they can't be used as single frames.

Useful flags: `--size WxH`, `--crf` (quality, lower is bigger), `--timespan`, `--max-workers`.

### One camera on its own

`--view` picks which of the three exports to stitch, so you can make a video of just the front camera - 2,000 selfies from the same phone at arm's length, which lines up far more consistently than the back camera does:

```sh
python make_video.py --view selfie-view   # -> output/bereals-selfie-view.mp4
python make_video.py --view main-view     # -> output/bereals-main-view.mp4
```

The default filename follows the view, so these never overwrite each other or your `bereals.mp4`.

### Picking a speed

`--fps` is the one worth thinking about, because it decides how long each BeReal is on screen:

| `--fps` | Per BeReal | ~2,200 BeReals | Feels like |
|---|---|---|---|
| 10 (default) | 0.1s | 3m 40s | A flipbook - a year goes past in seconds |
| 6 | 0.17s | 6m 5s | Still fast, but faces register |
| 4 | 0.25s | 9m 10s | You can actually look at each one |
| 2 | 0.5s | 18m 20s | A slideshow |

`-o` writes to a different file, so you can keep several cuts side by side rather than overwriting the last one:

```sh
python make_video.py --date-label                                # output/bereals.mp4
python make_video.py --date-label --fps 4 -o output/bereals-slow.mp4
```

`--date-label` is worth adding on the slower cuts especially - at 0.1s a frame the date is a blur, but with a quarter second to read it, it turns the video into a timeline.

This needs **ffmpeg** (`apt install ffmpeg` / `brew install ffmpeg` / [ffmpeg.org](https://ffmpeg.org/), or `--ffmpeg-path`). If your build has no libx264 - conda's doesn't - it falls back to libopenh264 at `--bitrate` instead, which still writes a normal MP4.

## Timezones

Each photo's time comes from the GPS coordinates BeReal recorded with it, so it lands in whatever timezone you were actually standing in.

Not every record has GPS - realmojis never do, and some memories don't either. Those fall back to a **hardcoded `Europe/London`**. If you don't live in the UK, change this line in `bereal_exporter.py` before running anything, or those photos get the wrong time (and, near midnight, the wrong day):

```python
local_tz = pytz.timezone('Europe/London')
```

There's no command-line flag for it yet.

## Interactive conversation processing

Conversation images don't record which camera is which, so the script guesses from filenames, dimensions and patterns. It's usually right, but not always. To correct it by hand:

```sh
python bereal_exporter.py --conversations-only --interactive-conversations           # terminal
python bereal_exporter.py --conversations-only --interactive-conversations --web-ui  # browser
```

The web UI shows both images side by side; click the one that should be the selfie view and it carries on. Much easier than the terminal version.

## License

MIT - see [LICENSE](LICENSE).
