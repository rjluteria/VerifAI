import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZIP_DEFLATED, ZipFile


def service_origin(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or not url.hostname.endswith(".onrender.com")
        or url.username
        or url.password
        or url.port
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError("Use the exact HTTPS Render service origin.")
    return "https://" + url.hostname


def main():
    parser = argparse.ArgumentParser(description="Package the configured extension.")
    parser.add_argument(
        "--backend-origin", help="Developer-only Render origin override for this ZIP."
    )
    parser.add_argument("--output", type=Path, help="Developer package destination.")
    parser.add_argument(
        "--benchmark-timing",
        action="store_true",
        help="Developer-only visible panel render clock for native acceptance.",
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "extension/manifest.json").read_text())
    assert "<all_urls>" not in json.dumps(manifest)
    assert manifest["manifest_version"] == 3
    replacements = {}
    config = (root / "extension/config.js").read_text()
    config, count = re.subn(
        r"export const BENCHMARK_TIMING = (?:true|false);",
        "export const BENCHMARK_TIMING = "
        + ("true" if args.benchmark_timing else "false")
        + ";",
        config,
    )
    assert count == 1
    content = (root / "extension/content.js").read_text()
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
    if args.backend_origin:
        origin = service_origin(args.backend_origin)
        config, count = re.subn(
            r'backend\("https://[^"\n]+"\)',
            lambda match: "backend(" + json.dumps(origin) + ")",
            config,
        )
        assert count == 1
        manifest["optional_host_permissions"] = [origin + "/*"]
        replacements["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    if config.encode() != (root / "extension/config.js").read_bytes():
        replacements["config.js"] = config.encode()
    output = args.output or root / "dist" / ("verifai-" + manifest["version"] + ".zip")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted((root / "extension").iterdir()):
            if path.is_file():
                archive.writestr(
                    path.name, replacements.get(path.name, path.read_bytes())
                )
    print("Extension package created.")


if __name__ == "__main__":
    main()
