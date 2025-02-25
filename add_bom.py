#!/usr/bin/env python3
import os
import sys

BOM = b'\xef\xbb\xbf'


def add_bom_to_file(file_path: str):
    """Adds BOM to the file if it doesn't already contain it."""
    with open(file_path, 'rb') as f:
        content = f.read()
    if not content.startswith(BOM):
        print(f"Adding BOM to: {file_path}")
        with open(file_path, 'wb') as f:
            f.write(BOM + content)
    else:
        print(f"BOM already present: {file_path}")


def process_directory(directory: str):
    """Recursively processes all .yml files in the given directory."""
    for root, _, files in os.walk(directory):
        for file in files:
            if file.lower().endswith(".yml"):
                add_bom_to_file(os.path.join(root, file))


if __name__ == "__main__":
    # Process all arguments as files or directories.
    for path in sys.argv[1:]:
        if os.path.isfile(path):
            add_bom_to_file(path)
        elif os.path.isdir(path):
            process_directory(path)
        else:
            print(f"Error: '{path}' is neither a file nor a directory.")
