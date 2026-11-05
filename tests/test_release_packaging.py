"""Guard both maintained release lines without starting any service."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_explicit_context_policy_lists_both_maintained_patch_inputs(self):
        rules = (ROOT / '.dockerignore').read_text().splitlines()
        for path in ('build/Dockerfile.password-revocation',
                     'build/Dockerfile.v4-password-revocation',
                     'patches/casdoor-3.152.0-password-revocation.patch',
                     'patches/casdoor-4.25.0-password-revocation-scoped-policy.patch',
                     'tests/v4-revocation/upstream.tar.gz'):
            self.assertIn('!' + path, rules, path)

    def test_ci_keeps_v3_and_v4_builds_without_publish(self):
        workflow = (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
        self.assertIn('  password-revocation:', workflow)
        self.assertIn('  v4-backport:', workflow)
        self.assertNotIn('docker push', workflow)
        self.assertNotIn('push: true', workflow)

    def test_candidate_uses_final_scoped_patch_and_pinned_source(self):
        dockerfile = (ROOT / 'build/Dockerfile.v4-password-revocation').read_text()
        self.assertIn('COPY patches/casdoor-4.25.0-password-revocation-scoped-policy.patch ', dockerfile)
        self.assertIn('528a0213f01caf70b9f41009cbf7b2f67bdd67ec', dockerfile)
        self.assertIn('fc80ec9398d19d333cabb258b824c6c4614248f943800c31366ef76a4660f7ad', dockerfile)


if __name__ == '__main__':
    unittest.main()
