"""Exercise Docker ignore semantics using dummy inputs only, never real credentials."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = (
    'build/Dockerfile.password-revocation', 'build/Dockerfile.v4-password-revocation',
    'patches/casdoor-3.152.0-password-revocation.patch',
    'patches/casdoor-4.25.0-password-revocation-scoped-policy.patch',
    'patches/casdoor-4.25.0-credentialed-origins.patch',
    'tests/v4-revocation/upstream.tar.gz', 'tests/iam_v4/requirements.lock',
)
DENIED = ('.env', 'conf/app.conf', 'patches/private.secret', 'build/unreviewed.txt',
          'tests/v4-revocation/fixture.json', 'tests/iam_v4/.runs/fixture.json')


def main():
    with tempfile.TemporaryDirectory(prefix='mb-casd-context-') as temporary:
        owned = Path(temporary).resolve()
        assert owned.is_relative_to(Path(tempfile.gettempdir()).resolve())
        context = owned / 'context'
        context.mkdir()
        for name in (*ALLOWED, *DENIED):
            file = context / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('dummy synthetic build-context sentinel\n')
        (context / '.dockerignore').write_bytes((ROOT / '.dockerignore').read_bytes())
        (context / 'Dockerfile').write_text('FROM scratch\nCOPY . /snapshot/\n')
        output = owned / 'export'
        result = subprocess.run(['docker', 'build', '--network', 'none', '--progress', 'plain',
                                 '--output', 'type=local,dest=' + str(output), str(context)],
                                capture_output=True, timeout=90)
        if result.returncode:
            raise RuntimeError('Dummy context build failed; no real configuration was included')
        files = {p.relative_to(output / 'snapshot').as_posix() for p in (output / 'snapshot').rglob('*') if p.is_file()}
        missing = set(ALLOWED) - files
        leaked = set(DENIED) & files
        assert not missing and not leaked, f'missing={sorted(missing)}; unexpected={sorted(leaked)}'
        print(f'Docker context verified: {len(ALLOWED)} required inputs present; {len(DENIED)} private/unreviewed sentinels excluded')


if __name__ == '__main__':
    main()
