import argparse
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


def main():
    parser = argparse.ArgumentParser(description="Package the configured extension.")
    parser.add_argument("--output", type=Path, help="Developer package destination.")
    parser.add_argument(
        "--benchmark-timing",
        action="store_true",
        help="Developer-only visible panel render clock for native acceptance.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (root / "extension/manifest.json").read_text(encoding="utf-8")
    )
    assert "<all_urls>" not in json.dumps(manifest)
    assert manifest["manifest_version"] == 3
    replacements = {}
    config = (root / "extension/config.js").read_text(encoding="utf-8")
    config, count = re.subn(
        r"export const BENCHMARK_TIMING = (?:true|false);",
        "export const BENCHMARK_TIMING = "
        + ("true" if args.benchmark_timing else "false")
        + ";",
        config,
    )
    assert count == 1
    content = (root / "extension/content.js").read_text(encoding="utf-8")
    content, count = re.subn(
        r"const BENCHMARK_TIMING = (?:true|false);",
        "const BENCHMARK_TIMING = "
        + ("true" if args.benchmark_timing else "false")
        + ";",
        content,
    )
    assert count == 1
    if content.encode() != (root / "extension/content.js").read_bytes():
        replacements["content.js"] = content.encode()
    if config.encode() != (root / "extension/config.js").read_bytes():
        replacements["config.js"] = config.encode()
    output = args.output or root / "dist" / ("verifai-" + manifest["version"] + ".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted((root / "extension").iterdir()):
            if path.is_file():
                entry = ZipInfo(path.name, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                archive.writestr(entry, replacements.get(path.name, path.read_bytes()))
    print("Extension package created.")


if __name__ == "__main__":
    main()
