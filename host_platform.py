"""Host paths and nonblocking locks; no app modification or process launch."""
import errno
import os
import sys
from contextlib import contextmanager
from pathlib import Path


class LockBusy(RuntimeError):
    """Another process holds the requested lock."""


def _windows_lock_busy(error):
    # Preserve explicit Windows access-denied errors. CRT locking commonly reports
    # contention as EACCES without winerror; file-open permission errors never enter
    # this handler, because opening the file occurs before lock acquisition.
    winerror = getattr(error, 'winerror', None)
    if winerror not in (None, 0):
        return winerror in (32, 33)
    return error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)


@contextmanager
def file_lock(path, busy_message):
    """Lock a file without waiting, yielding its stream until the lock is released.

    The parent directory must already exist. Windows locks byte zero; POSIX uses
    flock. Lock-file contents are private implementation details and are preserved.
    """
    fd = os.open(Path(path), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, 'r+b', buffering=0) as stream:
        if sys.platform == 'win32':
            import msvcrt
            try:
                if os.fstat(stream.fileno()).st_size == 0:
                    stream.write(b'\0')
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                if _windows_lock_busy(exc):
                    raise LockBusy(busy_message) from exc
                raise
            try:
                yield stream
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    raise LockBusy(busy_message) from exc
                raise
            try:
                yield stream
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def app_paths(asar):
    """Resolve packaged app companions from the ASAR layout, not this host's OS."""
    asar = Path(asar)
    resources = asar.parent
    if asar.name.lower() != 'app.asar' or resources.name.lower() != 'resources':
        raise ValueError('Unsupported app layout; pass --asar pointing to resources/app.asar')
    root = resources.parent
    if root.name == 'Contents':
        return {
            'executable': root / 'MacOS/ZCode',
            'cli': resources / 'glm/zcode.cjs',
            'fuse_binary': root / 'Frameworks/Electron Framework.framework/Electron Framework',
            'platform': 'darwin',
        }
    return {
        'executable': root / 'ZCode.exe',
        'cli': resources / 'glm/zcode.cjs',
        'fuse_binary': root / 'ZCode.exe',
        'platform': 'win32',
    }


def default_asar():
    """Find a unique installed Windows app, or return the ordinary install path.

    Multiple installations (including Squirrel versions) require explicit choice;
    never guess which copy the user is running.
    """
    if sys.platform != 'win32':
        return Path('/Applications/ZCode.app/Contents/Resources/app.asar')
    local = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData/Local')
    ordinary = local / 'Programs/ZCode/resources/app.asar'
    roots = [local / 'Programs/ZCode', local / 'ZCode']
    for key in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value) / 'ZCode')
    found = {}
    for root in roots:
        candidates = [root / 'resources/app.asar', *root.glob('app-*/resources/app.asar')]
        for candidate in candidates:
            if candidate.is_file():
                resolved = candidate.resolve()
                found[os.path.normcase(str(resolved))] = resolved
    if len(found) > 1:
        raise ValueError('Multiple ZCode installations found; select one with --asar: '
                         + ', '.join(str(path) for path in found.values()))
    return next(iter(found.values())) if found else ordinary
