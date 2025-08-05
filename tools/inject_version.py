import re
import sys
from pathlib import Path

if len(sys.argv) != 3:
    print("Usage: inject_version.py <file> <tag>")
    sys.exit(1)

file_path = Path(sys.argv[1])
tag = sys.argv[2]

# Parse version and suffix
tag_match = re.match(r"v(\d+)\.(\d+)\.(\d+)(?:-(\w+))?", tag)
if not tag_match:
    print(f"Tag {tag} does not match expected format vX.Y.Z or vX.Y.Z-suffix")
    sys.exit(1)

major, minor, patch, suffix = tag_match.groups()
release_type = "mobase.ReleaseType.FINAL" if suffix is None else "mobase.ReleaseType.BETA"

# Replace version method
pattern = re.compile(r"def version\(self\):\n\s*return mobase.VersionInfo\([^)]*\)")

with file_path.open("r", encoding="utf-8") as f:
    content = f.read()

new_version = f"def version(self):\n        return mobase.VersionInfo({major}, {minor}, {patch}, {release_type})"

content, count = pattern.subn(new_version, content)
if count == 0:
    print("No version method found to replace.")
    sys.exit(1)

with file_path.open("w", encoding="utf-8") as f:
    f.write(content)

print(f"Injected version {major}.{minor}.{patch} ({release_type}) into {file_path}")
