"""Bounded, process-local URL summaries for the SQLite JSON projections."""
import json
import os
import stat
import sys
from collections import OrderedDict
from threading import Lock
from time import time_ns
from urllib.parse import unquote_plus

from api_test.interoperability import SENSITIVE


def case_url(document):
    request = document.get('request')
    url = request.get('url') if isinstance(request, dict) else None
    return url if isinstance(url, str) else ''


def read_case_url(source):
    return case_url(json.loads(source.read().decode('utf-8')))


def _stable_version(info, stable_before):
    if not stat.S_ISREG(info.st_mode) or not info.st_ino or not 0 < info.st_ctime_ns < stable_before:
        return None
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns


def _direct_path(root, reference, parents):
    # Only ordinary, slash-separated relative paths qualify for reuse. Aliases
    # and symlinks still go through the caller's full path policy on every read.
    # Windows st_ctime is creation time on supported Python versions. A same-size
    # external edit can restore mtime there, so use the verified reader directly.
    if os.name != 'posix':
        return None
    if not isinstance(reference, str) or not reference.endswith('.json') or reference.startswith('/'):
        return None
    if '\\' in reference or ':' in reference:
        return None
    parent, _, name = reference.rpartition('/')
    if parent not in parents:
        directory = os.path.join(root, parent) if parent else root
        clean = not parent or all(part not in ('', '.', '..', '_workspaces') for part in parent.split('/'))
        parents[parent] = directory if clean and os.path.realpath(directory) == directory else None
    directory = parents[parent]
    return os.path.join(directory, name) if directory is not None else None


class CaseProjectionCache:
    def __init__(self, max_entries=32_768):
        self._entries = OrderedDict()
        self._lock = Lock()
        self._limit = max_entries

    def _cached_url(self, key, stable_before):
        try:
            info = os.lstat(key)
        except OSError:
            return None
        version = _stable_version(info, stable_before)
        if version is None:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None and entry[0] == version:
                self._entries.move_to_end(key)
                return entry[1]
        return None

    def _remember(self, key, version, url):
        # Retain only short public summaries. Userinfo, fragments and known credential
        # patterns bypass retention while the original URL is still returned to its caller.
        small = sys.getsizeof(key) + sys.getsizeof(url) <= 1024
        retain = small and '@' not in url and '#' not in url and not SENSITIVE.search(unquote_plus(url))
        with self._lock:
            self._entries.pop(key, None)
            if retain:
                self._entries[key] = (version, url)
                if len(self._entries) > self._limit:
                    self._entries.popitem(last=False)

    def summaries(self, root, references, resolve_file, read_url=read_case_url):
        resolved_root = os.path.realpath(root)
        # Do not publish a fingerprint in the same filesystem clock tick as a write.
        # This matters on mounts with coarse change timestamps and preserved mtimes.
        stable_before = time_ns() - 2_000_000_000
        parents, details = {}, {}
        for reference in references:
            key = _direct_path(resolved_root, reference, parents)
            url = self._cached_url(key, stable_before) if key is not None else None
            if url is None:
                path = resolve_file(root, reference)
                with path.open('rb') as source:
                    reusable = key is not None and key == os.fspath(path)
                    version = _stable_version(os.fstat(source.fileno()), stable_before) if reusable else None
                    url = read_url(source)
                    if version is not None and _stable_version(os.fstat(source.fileno()), stable_before) == version:
                        self._remember(key, version, url)
            details[reference] = {'url': url}
        return details
