import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "extension/manifest.json").read_text())
assert "<all_urls>" not in json.dumps(manifest)
assert manifest["manifest_version"] == 3
output = root / "dist"
output.mkdir(exist_ok=True)
with ZipFile(
    output / ("verifai-" + manifest["version"] + ".zip"), "w", ZIP_DEFLATED
) as archive:
    for path in sorted((root / "extension").iterdir()):
        if path.is_file():
            archive.write(path, path.name)
print("Extension package created.")
