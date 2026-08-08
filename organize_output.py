"""
Sorts an exported folder into one subfolder per view.

bereal_exporter.py writes all three files of each BeReal side by side:

    posts/2024-07-01_22-46-46_main-view.webp
    posts/2024-07-01_22-46-46_selfie-view.webp
    posts/2024-07-01_22-46-46_composited.webp

which is awkward to upload anywhere, because most photo libraries treat the
three as three separate items. This splits them up so you can upload just the
folder you actually want:

    main-view/     back camera on its own
    selfie-view/   front camera on its own
    composited/    the two combined, the way BeReal displayed it

Usage:
    python organize_output.py                  # sort ./output/posts
    python organize_output.py --dry-run        # show what would move
    python organize_output.py --copy           # leave the originals in place
    python organize_output.py --source output/conversations/<id>
"""

import argparse
import os
import shutil

# Filename suffix (before the extension) -> folder it belongs in.
VIEWS = {
    "_main-view": "main-view",
    "_selfie-view": "selfie-view",
    "_composited": "composited",
}


def init_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sort exported BeReal images into main-view/selfie-view/composited folders",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "-p",
        "--out-path",
        dest="out_path",
        type=str,
        default="./output",
        help="Export folder the view folders are created in (default ./output)",
    )
    parser.add_argument(
        "-s",
        "--source",
        type=str,
        help="Folder to sort (default <out-path>/posts)",
    )
    parser.add_argument(
        "--copy",
        default=False,
        action="store_true",
        help="Copy instead of moving, leaving the source folder untouched",
    )
    parser.add_argument(
        "--overwrite",
        default=False,
        action="store_true",
        help="Replace files already sitting in the destination folders",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        default=False,
        action="store_true",
        help="Report what would happen without touching anything",
    )
    return parser.parse_args()


def classify(filename: str) -> str:
    """
    Returns the view folder a file belongs in, or None if it isn't one of ours.
    """
    base = os.path.splitext(filename)[0]
    for suffix, folder in VIEWS.items():
        if base.endswith(suffix):
            return folder
    return None


def organize(source: str, out_path: str, copy: bool, overwrite: bool, dry_run: bool):
    if not os.path.isdir(source):
        raise FileNotFoundError(f"Source folder not found: {source}")

    moved = {folder: 0 for folder in VIEWS.values()}
    skipped = 0
    unrecognized = 0

    for filename in sorted(os.listdir(source)):
        src = os.path.join(source, filename)
        if not os.path.isfile(src):
            continue

        folder = classify(filename)
        if folder is None:
            unrecognized += 1
            continue

        destination_folder = os.path.join(out_path, folder)
        dst = os.path.join(destination_folder, filename)

        if os.path.exists(dst) and not overwrite:
            skipped += 1
            continue

        if dry_run:
            moved[folder] += 1
            continue

        os.makedirs(destination_folder, exist_ok=True)
        if copy:
            shutil.copy2(src, dst)
        else:
            # Not os.rename - the output folder may be on a different filesystem.
            shutil.move(src, dst)
        moved[folder] += 1

    verb = "Would sort" if dry_run else ("Copied" if copy else "Moved")
    total = sum(moved.values())
    print(f"{verb} {total} files from {source}")
    for folder, count in moved.items():
        print(f"  {folder + '/':<14} {count}")
    if skipped:
        print(f"  {skipped} already in place (use --overwrite to replace)")
    if unrecognized:
        print(f"  {unrecognized} files left alone (no view suffix in the name)")


if __name__ == "__main__":
    args = init_parser()
    out_path = args.out_path.rstrip("/")
    source = args.source.rstrip("/") if args.source else os.path.join(out_path, "posts")

    try:
        organize(source, out_path, args.copy, args.overwrite, args.dry_run)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        exit(1)
