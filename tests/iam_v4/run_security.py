"""One new all-synthetic, internal-only run; every identity client remains DCR."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

from candidate_image import resolve_candidate
import dcr_logout_probe as probe
from dcr_product_review import PREFIX

IMAGE = 'mb-casd-v4:local'
parser = argparse.ArgumentParser()
parser.add_argument('--tools-image', default='mb-casd-iam-v4-tools:local')
parser.add_argument('--run-tag', required=True)
parser.add_argument('--image', default=IMAGE)
parser.add_argument('--replica', action='store_true')
args = parser.parse_args()
assert args.tools_image == 'mb-casd-iam-v4-tools:local' or re.fullmatch(r'sha256:[0-9a-f]{64}', args.tools_image)
probe.r.TOOLS_IMAGE = args.tools_image
(HERE/'.runs').mkdir(exist_ok=True)
assert re.fullmatch('[a-z0-9-]{1,8}', args.run_tag)
args.image = resolve_candidate(args.image)
controller = PREFIX+(HERE/'controller.py').read_text()
assert not (HERE/'.runs'/args.run_tag).exists(), 'Never overwrite a prior run'
try:
    probe.run_fixture('mdm-e2e-v4-security-'+args.run_tag, HERE/'.runs'/args.run_tag,
       controller, image=args.image, fault_checks=True,
       self_logout_clients=('mdm-signing-login','mdm-signing-pm','mdm-signing-portal'),
       self_policy_clients=('mdm-signing-pm','mdm-signing-portal'),
       scoped_logout_clients=('mdm-signing-login','mdm-signing-pm','mdm-signing-portal'),
       refresh_clients=('mdm-signing-pm',), replica=args.replica)
except Exception as error:
    print(json.dumps({'status':'failed','error_type':type(error).__name__, 'private_details_suppressed':True}))
    raise SystemExit(1) from None
finally:
    out = HERE/'.runs'/args.run_tag
    if out.exists():
        inputs = out/'test-inputs.json'
        if not inputs.exists():
            inputs.write_text(json.dumps({'controller_sha256':hashlib.sha256(controller.encode()).hexdigest(),
              'image':args.image,'replica':args.replica,'temporary_grant':'only synthetic PM refresh_token',
              'signature_retried':False,'browser_test':False},indent=2))
        source_snapshot = out/'controller.snapshot.py'
        if not source_snapshot.exists():
            source_snapshot.write_text(controller, encoding='utf-8', newline='\n')
