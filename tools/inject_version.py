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

# Replace global version constants
patterns = {
    'VERSION_MAJOR': re.compile(r'VERSION_MAJOR\s*=\s*\d+'),
    'VERSION_MINOR': re.compile(r'VERSION_MINOR\s*=\s*\d+'),
    'VERSION_PATCH': re.compile(r'VERSION_PATCH\s*=\s*\d+'),
    'VERSION_RELEASE_TYPE': re.compile(r'VERSION_RELEASE_TYPE\s*=\s*mobase\.ReleaseType\.[A-Z]+'),
}

with file_path.open("r", encoding="utf-8") as f:
    content = f.read()

content, major_count = patterns['VERSION_MAJOR'].subn(f'VERSION_MAJOR = {major}', content)
content, minor_count = patterns['VERSION_MINOR'].subn(f'VERSION_MINOR = {minor}', content)
content, patch_count = patterns['VERSION_PATCH'].subn(f'VERSION_PATCH = {patch}', content)
content, type_count = patterns['VERSION_RELEASE_TYPE'].subn(f'VERSION_RELEASE_TYPE = {release_type}', content)

if not all([major_count, minor_count, patch_count, type_count]):
    print("One or more version constants not found to replace.")
    sys.exit(1)

with file_path.open("w", encoding="utf-8") as f:
    f.write(content)

print(f"Injected version {major}.{minor}.{patch} ({release_type}) into {file_path}")
