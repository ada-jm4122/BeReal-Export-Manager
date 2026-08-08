# BeReal Exporter

This python script doesn't export photos and realmojis from the social media platform BeReal directly - for that, you have to make a request to BeReal. See [this Reddit post](https://www.reddit.com/r/bereal_app/comments/19dl0yk/experiencetutorial_for_exporting_all_bereal/?utm_source=share&utm_medium=web3x&utm_name=web3xcss&utm_term=1&utm_content=share_button) for more information.

It processes the data from the BeReal export and exports the images with added metadata, such as the original date and location. Now supports posts, memories, realmojis, and conversation images with parallel processing for speed. Also has interactive modes for when you want to manually choose which camera is which for conversation images.

I'm gonna be upfront and say it's BeReal's fault the dates are wonky on the output files, idk why they chose to save the time like this:

        "takenTime": "2024-12-24T01:27:16.726Z",
        "berealMoment": "2024-12-23T22:39:05.327Z",

instead of the way everyone else always does it with UNIX Epoch time, but it makes it pretty hard to find out what time the picture was taken, and to properly tag the photos with the correct time. The script works the real local time out from the GPS coordinates on each photo - see [Timezones](#timezones) for the cases where it can't.

## Installation

1. Clone the repository:
    ```sh
    git clone https://github.com/ada-jm4122/BeReal-Export-Manager.git
    cd BeReal-Export-Manager
    ```

2. Install the required Python packages:
    ```sh
    pip install -r requirements.txt
    ```

3. Install `exiftool` and make sure it's on your `PATH`. This is **required**, not optional - the script writes all its metadata through it and will fail immediately without it.
    - Linux / WSL: `sudo apt install libimage-exiftool-perl`
    - macOS: `brew install exiftool`
    - Windows: download from [exiftool.org](https://exiftool.org/), or skip the PATH setup and pass `--exiftool-path C:\path\to\exiftool.exe`

    Check it worked:
    ```sh
    exiftool -ver
    ```

## Which BeReal download do I need?

When you request your data, BeReal may send you **two different files**. Only one of them is any use here:

| File | What it is | Use it? |
|---|---|---|
| A large `.zip` (hundreds of MB or more) named like `<userid>-<random>.zip` | Your actual photos plus `posts.json` / `memories.json` / `realmojis.json` | **Yes** |
| A small `<userid>_<timestamp>.json.gz` (tens of KB) | Analytics/telemetry - a log of `applicationOpened` events, your device model, and city-level location history. No photos at all. | No - ignore it |

If your download is only a few KB and unzips to lines of `{"event_type":"applicationOpened",...}`, that's the telemetry file. The photo archive is a separate download - check your other BeReal emails.

## Setting up the input folder

The script looks for a **subfolder** inside `input/`, so your export must sit one level deep. Note that BeReal's zip has *no wrapping folder* of its own - everything is at the zip root - so unzip it into a folder you create yourself:

```sh
mkdir -p input/export
unzip -o your-bereal-export.zip -d input/export
```

You should end up with this:

```
input/
└── export/            <- name doesn't matter, but this level must exist
    ├── memories.json
    ├── posts.json
    ├── realmojis.json
    ├── Photos/
    │   ├── post/
    │   └── realmoji/
    └── conversations/
        └── <conversation_id>/
```

Two things to know:

- **Don't unzip straight into `input/`.** If `memories.json` lands at `input/memories.json` the script only scans *subdirectories* and will fail with `No BeReal export folder found in input directory`.
- **Use `unzip -o`.** BeReal's archive contains *two different files both named `realmojis.json`* - a small one (your pinned instant realmojis) and a large one (your actual reactions). Without `-o`, unzip stops to ask you about the collision. With it, the larger correct one wins.

Only one export folder should be in `input/` at a time. If there are two, which one gets picked is arbitrary.

## Usage

Once your export is in place:
```sh
python bereal_exporter.py [OPTIONS]
```

That processes everything - posts, memories, realmojis and conversations - in parallel, writing to `./output`. A full export of a few thousand BeReals takes on the order of an hour or two, so consider testing on a single year first:

```sh
python bereal_exporter.py --year 2024
```

## Options

- `-v, --verbose`: Explain what is being done.
- `-t, --timespan`: Exports the given timespan. 
  - Valid format: `DD.MM.YYYY-DD.MM.YYYY`.
  - Wildcards can be used: `DD.MM.YYYY-*`.
  - Both dates are read as midnight, so the end date is effectively **exclusive** - `01.07.2026-04.07.2026` will not include a BeReal taken at 00:30 on the 4th. Set the end a day later than you think you need.
- `-y, --year`: Exports the given year.
- `-p, --out-path`: Set a custom output path (default is `./output`).
- `--input-path`: Set the input folder path containing BeReal export (default `./input`).
- `--exiftool-path`: Set the path to the ExifTool executable (needed if it isn't on the $PATH).
- `--max-workers`: Maximum number of parallel workers (default 4).
- `--no-memories`: Don't export the memories.
- `--no-realmojis`: Don't export the realmojis.
- `--no-posts`: Don't export the posts.
- `--no-conversations`: Don't export the conversations.
- `--conversations-only`: Export only conversations (for debugging).
- `--interactive-conversations`: Manually choose front/back camera for conversation images.
- `--web-ui`: Use web UI for interactive conversation selection (requires `--interactive-conversations`).

## Timezones

Each photo's timestamp is worked out from the GPS coordinates BeReal recorded with it, so it comes out in whatever timezone you were actually standing in.

Not every record has GPS though - realmojis never do, and a fraction of memories don't either. Those fall back to a **hardcoded default of `Europe/London`**. If you don't live in the UK, change this line in `bereal_exporter.py` before you run anything, or those photos will be stamped with the wrong time (and, if taken near midnight, the wrong day):

```python
local_tz = pytz.timezone('Europe/London')
```

There's no command-line flag for it yet.

## Examples

1. Export everything (default behavior):
    ```sh
    python bereal_exporter.py
    ```

2. Export data for the year 2022:
    ```sh
    python bereal_exporter.py --year 2022
    ```

3. Export data for a specific timespan:
    ```sh
    python bereal_exporter.py --timespan '04.01.2022-31.12.2022'
    ```

4. Export to a custom output path:
    ```sh
    python bereal_exporter.py --out-path /path/to/output
    ```

5. Use a different input folder. Point this at the folder *containing* your export folder, not at the export itself - the script still expects one level of nesting:
    ```sh
    # if your export lives at /media/backup/bereal/export/memories.json
    python bereal_exporter.py --input-path /media/backup/bereal
    ```

6. Use portable exiftool:
    ```sh
    python bereal_exporter.py --exiftool-path /path/to/exiftool.exe
    ```

7. Export only memories and posts (skip realmojis and conversations):
    ```sh
    python bereal_exporter.py --no-realmojis --no-conversations
    ```

8. Debug conversations only:
    ```sh
    python bereal_exporter.py --conversations-only
    ```

9. Use more workers for faster processing:
    ```sh
    python bereal_exporter.py --max-workers 8
    ```

10. Interactive conversation selection (command line):
    ```sh
    python bereal_exporter.py --conversations-only --interactive-conversations
    ```

11. Interactive conversation selection (web UI):
    ```sh
    python bereal_exporter.py --conversations-only --interactive-conversations --web-ui
    ```

## Interactive Conversation Processing

For conversation images, the script tries to automatically detect which image should be the main view vs selfie view, but sometimes it gets it wrong. That's where the interactive modes come in handy.

**Automatic Detection**: The script looks at filenames, image dimensions, and patterns to guess which camera is which. Works most of the time but not always.

**Interactive Mode**: You can manually choose which image should be the selfie view (front camera overlay):
- **Command Line** (`--interactive-conversations`): Opens images in your system viewer, you choose via keyboard
- **Web UI** (`--interactive-conversations --web-ui`): Opens a web page where you just click on the selfie image

The web UI is pretty nice - shows both images side by side, you click the one that should be the selfie view, and it automatically continues processing. Much easier than the command line version.

**File Naming**: All images get descriptive names so you know what's what:
- `2022-09-10_16-35-30_main-view.webp` (back camera)
- `2022-09-10_16-35-30_selfie-view.webp` (front camera) 
- `2022-09-10_16-35-30_composited.webp` (combined image with selfie overlaid)

## What Gets Exported

You get this in `output/`:

```
output/
├── posts/                  every BeReal, 3 files each (see below)
├── realmojis/              your reaction selfies
└── conversations/<id>/     images sent in private conversations
```

**Every BeReal produces three files**, not one:

- `2022-09-10_16-35-30_main-view.webp` - back camera
- `2022-09-10_16-35-30_selfie-view.webp` - front camera
- `2022-09-10_16-35-30_composited.webp` - the two combined, front overlaid on back with rounded corners and a black border, the way BeReal displayed it

So ~2,000 BeReals becomes ~6,000 files. Worth knowing before you import the lot into a photo library, where all three will show up as separate items - most people only want the `_composited` ones. The filenames make that easy to filter on afterwards.

Posts and memories are two views of the same BeReals (memories carry richer metadata - location and multiple timestamps), and both write into `posts/`. The script detects the overlap so you don't get duplicates.

All images get EXIF metadata written with:
- `DateTimeOriginal` / `CreateDate` set to the local time the photo was taken
- GPS coordinates, where BeReal recorded them

A small number of images referenced in the JSON are simply missing from BeReal's archive. Those print `File not found in expected locations:` and are skipped; the export carries on.

## Performance

Uses parallel processing with configurable worker threads (default 4) for faster exports. Progress bars show real-time status. On a decent machine, expect to process hundreds of images per minute. If you have a fast SSD and good CPU, try bumping up `--max-workers` to 8 or more.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
