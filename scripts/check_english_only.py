"""Fail CI when repository text files contain Persian or Arabic-script characters."""

from pathlib import Path
import subprocess
import sys

SCRIPT_RANGES = ((0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
                 (0xFB50, 0xFDFF), (0xFE70, 0xFEFF))
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".ini", ".txt", ".json", ".csv", ".sh"}


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).decode("utf-8").split("\0")
    violations = []
    for filename in tracked:
        if not filename:
            continue
        path = Path(filename)
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, 1):
            if any(start <= ord(char) <= end for char in line for start, end in SCRIPT_RANGES):
                violations.append(f"{filename}:{number}")
    if violations:
        print("Non-English Arabic-script text found in tracked repository files:")
        print("\n".join(violations))
        return 1
    print("Language guard passed: no Arabic-script text in tracked source files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
