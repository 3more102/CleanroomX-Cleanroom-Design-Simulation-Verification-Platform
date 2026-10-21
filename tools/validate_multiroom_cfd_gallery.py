#!/usr/bin/env python3
"""Check that checked-in multiroom CFD screenshots and README references remain intact."""
from pathlib import Path
import hashlib
import json
import struct

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'docs' / 'images' / 'multiroom-cfd'
MANIFEST = BASE / 'manifest.json'

def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    readme = (ROOT / 'README.md').read_text(encoding='utf-8')
    gallery = (ROOT / 'docs' / 'MULTIROOM_CFD_GALLERY.md').read_text(encoding='utf-8')
    assert '<!-- cleanroomx-multiroom-cfd-gallery:start -->' in readme
    assert '<!-- cleanroomx-multiroom-cfd-gallery:end -->' in readme
    for asset in manifest['assets']:
        p = BASE / asset['file']
        data = p.read_bytes()
        assert data[:8] == b'\x89PNG\r\n\x1a\n', p
        w,h = struct.unpack('>II',data[16:24])
        assert (w,h) == (asset['width'],asset['height']), p
        assert len(data) == asset['bytes'], p
        assert hashlib.sha256(data).hexdigest() == asset['sha256'], p
        assert f'docs/images/multiroom-cfd/{asset["file"]}' in readme, p
        assert f'images/multiroom-cfd/{asset["file"]}' in gallery, p
        print(f'PASS {asset["file"]}: {w}x{h}, {len(data)} bytes')
    print('PASS six screenshots, README references, documentation, and SHA-256 integrity')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())