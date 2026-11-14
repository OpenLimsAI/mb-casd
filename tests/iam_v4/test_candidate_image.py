import unittest
from candidate_image import verify_metadata


class CandidateImageTests(unittest.TestCase):
    def test_new_image_id_requires_the_exact_verified_binary(self):
        labels = {'ai.openlims.casdoor.source': '528a0213f01caf70b9f41009cbf7b2f67bdd67ec',
                  'ai.openlims.casdoor.patch': 'password-revocation-own-policy-device-v11-cors-v1'}
        with self.assertRaises(ValueError):
            verify_metadata('sha256:' + 'a' * 64, labels, '0' * 64)

    def test_matching_labels_never_substitute_for_binary_verification(self):
        with self.assertRaises(ValueError):
            verify_metadata('sha256:' + 'a' * 64, {}, '5eb841954c0f06e7746b7f5bc5fe7ca83fecaa79bce05708991e99f4804e48c1')

    def test_noncanonical_image_identifier_is_rejected(self):
        with self.assertRaises(ValueError):
            verify_metadata('image:latest', {}, '')

    def test_metadata_only_rebuild_preserves_the_binary_contract(self):
        labels = {'ai.openlims.casdoor.source': '528a0213f01caf70b9f41009cbf7b2f67bdd67ec',
                  'ai.openlims.casdoor.patch': 'password-revocation-own-policy-device-v11-cors-v1'}
        image = 'sha256:' + 'b' * 64
        self.assertEqual(verify_metadata(image, labels, '5eb841954c0f06e7746b7f5bc5fe7ca83fecaa79bce05708991e99f4804e48c1'), image)
