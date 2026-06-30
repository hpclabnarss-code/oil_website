#!/usr/bin/env python3
"""
Group files by base name and compress each group into a ZIP archive.

Usage:
    python group_compress.py [directory]

If no directory is given, the current working directory is used.
"""

import os
import sys
import zipfile
from collections import defaultdict

def get_base_name(filename):
    """
    Return the base name of a file (without extension).
    Uses os.path.splitext to remove the last extension.
    For files with multiple extensions (e.g., .tar.gz), only the last is removed.
    """
    return os.path.splitext(filename)[0]

def compress_group(group_name, file_paths, output_dir):
    """
    Compress a list of files into a ZIP archive named group_name.zip.
    The archive is placed in output_dir.
    Returns the path to the created archive.
    """
    zip_path = os.path.join(output_dir, f"{group_name}.zip")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for fpath in file_paths:
            # Store the file with only its base name in the archive
            arcname = os.path.basename(fpath)
            zf.write(fpath, arcname=arcname)
    return zip_path

def main():
    # Determine target directory
    target_dir = sys.argv[1] if len(sys.argv) > 1 else os.getcwd()
    if not os.path.isdir(target_dir):
        print(f"Error: '{target_dir}' is not a valid directory.", file=sys.stderr)
        sys.exit(1)

    # Group files by base name
    groups = defaultdict(list)
    for entry in os.listdir(target_dir):
        full_path = os.path.join(target_dir, entry)
        if not os.path.isfile(full_path):
            continue          # skip directories, symlinks, etc.
        # Skip existing zip files to avoid re‑compressing them
        if entry.lower().endswith('.zip'):
            continue
        base = get_base_name(entry)
        groups[base].append(full_path)

    # Compress each group (only groups with at least 2 files)
    compressed = []
    for base, files in groups.items():
        if len(files) < 2:
            continue          # only group files that have "the same name"
        zip_path = compress_group(base, files, target_dir)
        compressed.append(zip_path)

    # Report results
    if compressed:
        print(f"Created {len(compressed)} archive(s):")
        for z in compressed:
            print(f"  {z}")
    else:
        print("No groups with multiple files found.")

if __name__ == "__main__":
    main()
