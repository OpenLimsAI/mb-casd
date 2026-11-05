"""Invalid targets must be rejected before any Docker or fixture mutation."""
from pathlib import Path
from unittest import TestCase, main, mock

import dcr_logout_probe as probe


class FixtureSafetyTests(TestCase):
    def test_non_synthetic_run_id_never_invokes_docker(self):
        with mock.patch.object(probe.r, 'docker') as docker:
            with self.assertRaises(AssertionError):
                probe.run_fixture('maibo', Path('/not-an-owned-run'), '')
            docker.assert_not_called()

    def test_arbitrary_output_directory_never_invokes_docker(self):
        with mock.patch.object(probe.r, 'docker') as docker:
            with self.assertRaises(AssertionError):
                probe.run_fixture('mdm-e2e-unit-denial', Path('/not-an-owned-run'), '')
            docker.assert_not_called()

    def test_nested_output_escape_never_invokes_docker(self):
        with mock.patch.object(probe.r, 'docker') as docker:
            with self.assertRaises(AssertionError):
                probe.run_fixture('mdm-e2e-unit-denial', Path(__file__).parent / '.runs' / 'nested' / 'escape', '')
            docker.assert_not_called()


if __name__ == '__main__':
    main()
