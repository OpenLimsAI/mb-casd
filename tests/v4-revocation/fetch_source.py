"""Fetch only the official immutable release source, with checksum verification."""
import hashlib
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent
TARGET = HERE / 'upstream.tar.gz'
URL = 'https://api.github.com/repos/casdoor/casdoor/tarball/528a0213f01caf70b9f41009cbf7b2f67bdd67ec'
EXPECTED = 'fc80ec9398d19d333cabb258b824c6c4614248f943800c31366ef76a4660f7ad'
if TARGET.exists():
    assert hashlib.sha256(TARGET.read_bytes()).hexdigest() == EXPECTED, 'Existing archive differs; inspect instead of overwriting'
else:
    request = urllib.request.Request(URL, headers={'User-Agent': 'mb-casd-local-verification'})
    with urllib.request.urlopen(request, timeout=120) as response:
        data = response.read()
    assert hashlib.sha256(data).hexdigest() == EXPECTED, 'Official archive checksum differs; do not build'
    with TARGET.open('xb') as out:
        out.write(data)
print('Pinned official source archive checksum verified')
