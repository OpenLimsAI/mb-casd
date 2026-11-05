"""New immutable-run compatibility on the repaired candidate, never old evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent

from candidate_image import resolve_candidate
import dcr_logout_probe as probe
import self_policy_device_regression as policy
from password_v8_regression import controller as password_controller

parser = argparse.ArgumentParser()
parser.add_argument('--tools-image', default='mb-casd-iam-v4-tools:local')
parser.add_argument('--image', default='mb-casd-v4:local')
parser.add_argument('--mode', choices=['policy','default-off'], required=True)
parser.add_argument('--run-tag', required=True)
args = parser.parse_args()
assert args.tools_image == 'mb-casd-iam-v4-tools:local' or re.fullmatch(r'sha256:[0-9a-f]{64}', args.tools_image)
probe.r.TOOLS_IMAGE = args.tools_image
(HERE/'.runs').mkdir(exist_ok=True)
assert re.fullmatch('[a-z0-9-]{1,8}', args.run_tag)
image = resolve_candidate(args.image)
output = HERE/'.runs'/('compat-'+args.run_tag)
assert not output.exists(), 'Never overwrite historical evidence'
controller = policy.CONTROLLER if args.mode=='policy' else password_controller
kwargs = {'image':image}
if args.mode=='policy':
    kwargs.update(self_logout_clients=('mdm-signing-login','mdm-signing-pm','mdm-signing-portal'),
       self_policy_clients=('mdm-signing-pm','mdm-signing-portal'),
       scoped_logout_clients=('mdm-signing-login','mdm-signing-pm','mdm-signing-portal'))
try:
    probe.run_fixture('mdm-e2e-v4-compat-'+args.run_tag, output, controller, **kwargs)
except Exception as error:
    print(json.dumps({'status':'failed','error_type':type(error).__name__,'private_details_suppressed':True}))
    raise SystemExit(1) from None
finally:
    if output.exists():
        (output/'test-inputs.json').write_text(json.dumps({'image':image,'mode':args.mode,
            'controller_sha256':hashlib.sha256(controller.encode()).hexdigest(),
            'browser_test':False,'signature_retried':False},indent=2))
        (output/'controller.snapshot.py').write_text(controller, encoding='utf-8', newline='\n')
