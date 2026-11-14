"""Bind cold-built images to the reviewed binary, never merely a mutable tag."""
import json
import re
import subprocess

SOURCE = '528a0213f01caf70b9f41009cbf7b2f67bdd67ec'
BINARY_SHA256 = '5eb841954c0f06e7746b7f5bc5fe7ca83fecaa79bce05708991e99f4804e48c1'
PATCH = 'password-revocation-own-policy-device-v11-cors-v1'


def verify_metadata(identity, labels, binary_sha256):
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', identity)
            or labels.get('ai.openlims.casdoor.source') != SOURCE
            or labels.get('ai.openlims.casdoor.patch') != PATCH
            or binary_sha256 != BINARY_SHA256):
        raise ValueError('Image does not match the reviewed fixed v11+CORS binary/source contract')
    return identity


def resolve_candidate(reference):
    if not re.fullmatch(r'(?:sha256:[0-9a-f]{64}|mb-casd-v4:(?:local|ci))', reference):
        raise ValueError('Use a local canonical digest or the fixed local/CI build tag')

    def docker(*args):
        result = subprocess.run(['docker', *args], capture_output=True, timeout=60)
        if result.returncode:
            raise ValueError('Local candidate verification failed; no pull or fixture mutation attempted')
        return result.stdout.decode().strip()

    identity = docker('image', 'inspect', '--format', '{{.Id}}', reference)
    labels = json.loads(docker('image', 'inspect', '--format', '{{json .Config.Labels}}', identity)) or {}
    # No credentials/config/network are supplied; execute only a checksum utility.
    checksum = docker('run', '--pull=never', '--rm', '--network', 'none', '--entrypoint', 'sha256sum', identity, '/server').split()[0]
    return verify_metadata(identity, labels, checksum)
