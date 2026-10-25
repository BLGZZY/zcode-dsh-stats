"""Read-only checks before repairing a new official desktop version."""
import json
import mmap
from pathlib import Path
from install import read_file, read_header

SENTINEL = b'dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX'
SELECTORS = {b'data-composer-layout', b'data-session-id', b'data-usage-used', b'data-usage-max'}


def check_fuses(binary):
    # Electron's official v1 wire: version byte, length byte, then ASCII states.
    # https://github.com/electron/fuses/blob/main/src/config.ts (integrity index 4).
    with Path(binary).open('rb') as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
        offset = 0
        found = 0
        while (pos := data.find(SENTINEL, offset)) >= 0:
            found += 1
            wire = pos + len(SENTINEL)
            if wire + 7 > len(data) or data[wire] != 1 or data[wire + 1] < 5:
                raise ValueError('Unsupported Electron fuse format')
            if data[wire + 2 + 4] != ord('0'):
                raise ValueError('Electron ASAR integrity validation is enabled or unknown; automatic patch refused')
            offset = wire + 2 + data[wire + 1]
        if not 1 <= found <= 2:
            raise ValueError('Cannot verify Electron ASAR integrity mode')


def check_target(asar):
    asar = Path(asar)
    pkg = json.loads(read_file(asar, 'package.json'))
    if pkg.get('name') != '@zcode/desktop' or pkg.get('main') not in ('out/main/index.js', './out/main/index.js'):
        raise ValueError('Unsupported ZCode package or entry point')
    framework = asar.parent.parent / 'Frameworks/Electron Framework.framework/Electron Framework'
    check_fuses(framework)
    found = set()

    def files(n, prefix=''):
        for name, child in n.get('files', {}).items():
            path = prefix + '/' + name
            if 'files' in child:
                yield from files(child, path)
            elif path.startswith('/out/renderer/') and path.endswith('.js') and not child.get('unpacked') and 'link' not in child:
                yield child

    with asar.open('rb') as stream:
        header, base = read_header(stream)
        for child in files(header):
            if child['size'] > 64 * 1024 * 1024:
                raise ValueError('Unexpected renderer bundle size')
            stream.seek(base + int(child['offset']))
            source = stream.read(child['size'])
            found.update(selector for selector in SELECTORS if selector in source)
            if found == SELECTORS:
                break
    if found != SELECTORS:
        raise ValueError('Updated composer structure is not supported; automatic patch refused')
    return {'version': pkg.get('version'), 'compatible': True}
