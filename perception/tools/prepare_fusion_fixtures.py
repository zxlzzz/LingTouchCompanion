"""Stage optional, locally held CS30 captures for the Android fusion regression."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', required=True, type=Path)
    args = parser.parse_args()
    source = args.samples.resolve()
    manifest = json.loads((ROOT/'tests/vision/fusion-samples.json').read_text(encoding='utf-8'))
    files = []
    for record in manifest:
        folders = [d for d in source.iterdir() if d.is_dir() and d.name.startswith(record['timestamp'])]
        if len(folders) != 1:
            parser.error(f"Expected one capture folder for {record['timestamp']}")
        for ext, expected in record['files'].items():
            kind = 'RGB' if ext == 'png' else 'Depth'
            path = folders[0]/f"RGBD_{kind}[{record['capture_index']}].{ext}"
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                parser.error(f'Capture missing or SHA-256 differs: {path}')
            files.append((path,f"{record['id']}.{ext}"))
    out = ROOT/'.build/vision/test-assets/fusion'
    out.mkdir(parents=True, exist_ok=True)
    for source_file, name in files:
        shutil.copyfile(source_file,out/name)
    print(f'Staged {len(files)} local files in {out}')

if __name__ == '__main__':
    main()
