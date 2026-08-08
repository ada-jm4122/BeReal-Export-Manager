"""
Stitches the composited BeReals into a single MP4, oldest first.

Reads the `_composited` images produced by bereal_exporter.py, normalizes them
to one frame size and pipes them to ffmpeg. Frames are ordered by the timestamp
in the filename, so the result runs chronologically.

Usage:
    python make_video.py                          # every composited BeReal
    python make_video.py --year 2024
    python make_video.py --fps 15 --date-label
    python make_video.py --limit 100 -o test.mp4  # quick preview

Requires ffmpeg on your PATH (or --ffmpeg-path).
"""

import argparse
import glob
import os
import shutil
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt

from PIL import Image, ImageDraw, ImageFont, ImageOps
from tqdm import tqdm

# Filenames are written as YYYY-MM-DD_HH-MM-SS_composited.ext
FILENAME_FORMAT = "%Y-%m-%d_%H-%M-%S"

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def init_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stitch the composited BeReals into one MP4",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--out-path",
        dest="out_path",
        type=str,
        default="./output",
        help="Export folder to read from (default ./output)",
    )
    parser.add_argument(
        "-s",
        "--source",
        action="append",
        help="Folder of composited images (repeatable)\n"
        "Default: <out-path>/composited, falling back to <out-path>/posts",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Path of the MP4 to write (default <out-path>/bereals.mp4)",
    )
    parser.add_argument(
        "-t",
        "--timespan",
        type=str,
        help="Only include the given timespan\n"
        "Valid format: 'DD.MM.YYYY-DD.MM.YYYY'\n"
        "Wildcards can be used: 'DD.MM.YYYY-*'",
    )
    parser.add_argument("-y", "--year", type=int, help="Only include the given year")
    parser.add_argument(
        "--fps",
        type=float,
        default=10,
        help="Frames per second (default 10, so ~3.5 minutes per 2000 BeReals)",
    )
    parser.add_argument(
        "--size",
        type=str,
        help="Frame size as WxH (default: the most common size in the source)",
    )
    parser.add_argument(
        "--date-label",
        dest="date_label",
        default=False,
        action="store_true",
        help="Burn the date of each BeReal into the bottom of the frame",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=20,
        help="x264 quality, lower is better and bigger (default 20)",
    )
    parser.add_argument(
        "--bitrate",
        type=str,
        default="12M",
        help="Bitrate used when the ffmpeg build has no libx264 (default 12M)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Only use the first N frames, for a quick preview",
    )
    parser.add_argument(
        "--max-workers",
        dest="max_workers",
        type=int,
        default=4,
        help="Threads used to decode and resize frames (default 4)",
    )
    parser.add_argument(
        "--ffmpeg-path",
        dest="ffmpeg_path",
        type=str,
        help="Path to the ffmpeg executable (needed if it isn't on the $PATH)",
    )
    args = parser.parse_args()
    if args.year and args.timespan:
        print("Timespan argument will be prioritized")
    return args


def init_time_span(args: argparse.Namespace) -> tuple:
    """
    Same timespan handling as bereal_exporter.py, so the flags behave alike.
    """
    if args.timespan:
        try:
            start_str, end_str = args.timespan.strip().split("-")
            start = (
                dt.fromtimestamp(0)
                if start_str == "*"
                else dt.strptime(start_str, "%d.%m.%Y")
            )
            end = dt.now() if end_str == "*" else dt.strptime(end_str, "%d.%m.%Y")
            return start, end
        except ValueError:
            raise ValueError("Invalid timespan format. Use 'DD.MM.YYYY-DD.MM.YYYY'.")
    elif args.year:
        return dt(args.year, 1, 1), dt(args.year, 12, 31)
    return dt.fromtimestamp(0), dt.now()


def find_sources(out_path: str, sources: list) -> list:
    """
    Works out which folders to read frames from.

    organize_output.py moves the composited images into their own folder, so
    look there first and fall back to the unsorted posts folder.
    """
    if sources:
        return [s.rstrip("/") for s in sources]

    for folder in ("composited", "posts"):
        candidate = os.path.join(out_path, folder)
        if os.path.isdir(candidate) and glob.glob(os.path.join(candidate, "*_composited.*")):
            return [candidate]

    raise FileNotFoundError(
        f"No composited images found in {out_path}. Run bereal_exporter.py first, "
        "or point --source at the folder holding them."
    )


def collect_frames(sources: list, time_span: tuple) -> list:
    """
    Returns the composited images in chronological order.

    The timestamp is taken from the filename rather than EXIF - it's already
    local time, and reading it costs nothing.
    """
    frames = []
    unreadable = 0

    for source in sources:
        if not os.path.isdir(source):
            raise FileNotFoundError(f"Source folder not found: {source}")

        for path in glob.glob(os.path.join(source, "*_composited.*")):
            stamp = os.path.basename(path).split("_composited")[0]
            try:
                taken_at = dt.strptime(stamp, FILENAME_FORMAT)
            except ValueError:
                unreadable += 1
                continue
            if time_span[0] <= taken_at <= time_span[1]:
                frames.append((taken_at, path))

    if unreadable:
        print(f"Ignored {unreadable} files whose name isn't a timestamp")

    frames.sort()
    return frames


def most_common_size(frames: list) -> tuple:
    """
    Picks the frame size to encode at: whatever most of the images already are,
    so the bulk of them are copied through without being resampled.
    """
    sizes = Counter()
    for _, path in frames:
        try:
            with Image.open(path) as img:  # header only, doesn't decode pixels
                sizes[img.size] += 1
        except Exception:
            continue

    if not sizes:
        raise ValueError("None of the frames could be read")

    width, height = sizes.most_common(1)[0][0]
    # x264 needs even dimensions for yuv420p
    return width - width % 2, height - height % 2


def load_font(width: int):
    """
    Returns a font sized relative to the frame, or None if none can be found.
    """
    size = max(16, width // 22)
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    try:
        return ImageFont.load_default(size)
    except TypeError:
        # Pillow < 10.1 can't scale the built-in font, so a label would be
        # unreadably small - better to leave it off.
        return None


def render_frame(frame, size, font) -> bytes:
    """
    Decodes one image and returns it as raw RGB bytes at the target size.

    Frames that are a different shape are fitted inside the target and padded
    with black rather than stretched.
    """
    taken_at, path = frame
    canvas = Image.new("RGB", size, (0, 0, 0))

    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.size != size:
                # contain() scales up as well as down, so the handful of frames
                # smaller than the target fill it instead of sitting in a border
                img = ImageOps.contain(img, size, Image.LANCZOS)
            canvas.paste(img, ((size[0] - img.width) // 2, (size[1] - img.height) // 2))
    except Exception as e:
        # A black frame keeps the timeline honest instead of dropping a day.
        tqdm.write(f"Could not read {path}: {e}")

    if font:
        draw = ImageDraw.Draw(canvas)
        label = taken_at.strftime("%-d %B %Y") if os.name != "nt" else taken_at.strftime("%d %B %Y")
        margin = size[1] // 25
        position = (size[0] // 2, size[1] - margin)
        # Cheap outline so the date stays readable over a bright photo
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            draw.text((position[0] + dx, position[1] + dy), label, font=font,
                      fill=(0, 0, 0), anchor="ms")
        draw.text(position, label, font=font, fill=(255, 255, 255), anchor="ms")

    return canvas.tobytes()


def pick_encoder(ffmpeg: str, crf: int, bitrate: str) -> list:
    """
    Returns the ffmpeg encoder arguments this build actually supports.

    libx264 is the one worth having, but plenty of builds ship without it -
    conda's, for one, which only has libopenh264. That still writes a playable
    H.264 MP4, it just takes a bitrate instead of a CRF.
    """
    try:
        encoders = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, check=False,
        ).stdout
    except OSError as e:
        raise RuntimeError(f"Could not run ffmpeg: {e}")

    if "libx264" in encoders:
        return ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf)]

    if "libopenh264" in encoders:
        print(
            f"This ffmpeg has no libx264, falling back to libopenh264 at {bitrate} "
            "(--crf is ignored; install a full ffmpeg build for better quality)"
        )
        return ["-c:v", "libopenh264", "-b:v", bitrate]

    print("No H.264 encoder found, falling back to MPEG-4 - the file will be larger")
    return ["-c:v", "mpeg4", "-q:v", "3"]


def build_video(frames, size, output, fps, encoder_args, ffmpeg, max_workers, font):
    """
    Pipes rendered frames straight into ffmpeg as raw video.

    Raw frames avoid a PNG encode per image, and streaming them keeps only a
    few in memory at a time - the whole export at once would be tens of GB.
    """
    command = [
        ffmpeg, "-y",
        # Its stderr is a pipe we only drain after the last frame, so keep it to
        # actual errors - progress stats would eventually fill the pipe buffer
        # and deadlock against our own writes to stdin.
        "-loglevel", "error", "-nostats",
        "-f", "rawvideo",
        "-pixel_format", "rgb24",
        "-video_size", f"{size[0]}x{size[1]}",
        "-framerate", str(fps),
        "-i", "-",
        *encoder_args,
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output,
    ]

    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # Decode a small batch ahead of the encoder rather than the whole list, so
    # memory stays bounded however many BeReals there are.
    batch_size = max(max_workers * 4, 8)

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            with tqdm(total=len(frames), desc="Encoding", unit="frame") as pbar:
                for start in range(0, len(frames), batch_size):
                    batch = frames[start:start + batch_size]
                    for data in executor.map(
                        lambda frame: render_frame(frame, size, font), batch
                    ):
                        process.stdin.write(data)
                        pbar.update(1)
                    pbar.set_postfix_str(f"At: {batch[-1][0].date()}")
        process.stdin.close()
    except BrokenPipeError:
        pass
    except KeyboardInterrupt:
        process.kill()
        raise

    if process.wait() != 0:
        print(process.stderr.read().decode(errors="replace")[-2000:])
        raise RuntimeError("ffmpeg failed")


if __name__ == "__main__":
    args = init_parser()
    out_path = args.out_path.rstrip("/")
    output = args.output or os.path.join(out_path, "bereals.mp4")

    ffmpeg = args.ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        print(
            "Error: ffmpeg not found. Install it (apt install ffmpeg / brew install ffmpeg / "
            "ffmpeg.org) or pass --ffmpeg-path."
        )
        exit(1)

    try:
        time_span = init_time_span(args)
        sources = find_sources(out_path, args.source)
        frames = collect_frames(sources, time_span)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}")
        exit(1)

    if not frames:
        print("No composited BeReals found in that time range.")
        exit(1)

    if args.limit:
        frames = frames[:args.limit]

    if args.size:
        try:
            width, height = (int(n) for n in args.size.lower().split("x"))
            size = (width - width % 2, height - height % 2)
        except ValueError:
            print("Error: --size must look like 1080x1440")
            exit(1)
    else:
        size = most_common_size(frames)

    font = load_font(size[0]) if args.date_label else None
    if args.date_label and font is None:
        print("No usable font found, continuing without date labels")

    print(
        f"Stitching {len(frames)} BeReals ({frames[0][0].date()} to {frames[-1][0].date()}) "
        f"at {size[0]}x{size[1]}, {args.fps} fps -> {output}"
    )

    try:
        encoder_args = pick_encoder(ffmpeg, args.crf, args.bitrate)
        build_video(frames, size, output, args.fps, encoder_args, ffmpeg, args.max_workers, font)
    except (RuntimeError, KeyboardInterrupt) as e:
        print(f"Error: {e}" if isinstance(e, RuntimeError) else "Interrupted")
        exit(1)

    duration = len(frames) / args.fps
    megabytes = os.path.getsize(output) / 1024 / 1024
    print(f"Wrote {output} - {duration:.0f}s, {megabytes:.1f} MB")
