"""Credentialed portal login against a new synthetic IAM and empty database."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from candidate_image import resolve_candidate
import dcr_logout_probe as probe
from dcr_product_review import PREFIX

HERE = Path(__file__).resolve().parent
ORIGINS = ('https://www.openlims.ai', 'https://pm.openlims.ai')
CONTROLLER = r'''
enabled = f['credentialed_origins_enabled']
approved = ('https://www.openlims.ai', 'https://pm.openlims.ai')
def readable(response, site):
 return (response.headers.get('access-control-allow-origin') == site
         and response.headers.get('access-control-allow-credentials') == 'true'
         and 'origin' in response.headers.get('vary', '').lower())

for site in approved:
 with client() as c:
  c.headers['Origin'] = site
  account = c.get('/api/get-account')
  preflight = c.options('/api/login', headers={'Access-Control-Request-Method':'POST',
      'Access-Control-Request-Headers':'content-type'})
  if not enabled:
   case('default_off_'+site, account.headers.get('access-control-allow-credentials') != 'true'
        and preflight.headers.get('access-control-allow-credentials') != 'true')
   continue
  case('anonymous_and_preflight_'+site, readable(account, site) and readable(preflight, site)
       and account.json().get('status') == 'error' and preflight.status_code == 200)
  app = 'mdm-signing-portal' if site == approved[0] else 'mdm-signing-pm'
  verifier = secrets.token_urlsafe(48); nonce = secrets.token_urlsafe(24)
  challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
  p = {'clientId':app, 'responseType':'code', 'redirectUri':f['callbacks'][app],
       'scope':'openid profile', 'state':secrets.token_urlsafe(24), 'nonce':nonce,
       'code_challenge':challenge, 'code_challenge_method':'S256'}
  body = {'type':'code', 'application':app, 'organization':org,
          'signinMethod':'Password', 'username':'e2e.signer', 'password':f['users']['signer']}
  # Match the production portal: direct credentialed simple POST, without a preceding IAM navigation.
  response = c.post('/api/login', params=p, content=json.dumps(body),
      headers={'Content-Type':'text/plain;charset=UTF-8'})
  result = response.json()
  if isinstance(result.get('data'), dict) and result['data'].get('required') is True:
   response = c.post('/api/grant-consent', json={'application':'admin/'+app, 'clientId':app,
       'grantedScopes':['openid','profile'], 'scope':p['scope'], 'signinMethod':'Password',
       'responseType':'code', 'redirectUri':p['redirectUri'], 'state':p['state'],
       'nonce':nonce, 'challenge':challenge})
   result = response.json()
  assert result.get('status') == 'ok' and isinstance(result.get('data'), str), 'Synthetic direct login failed'
  account = c.get('/api/get-account')
  case('direct_login_and_cookie_reuse_'+site, readable(response, site) and readable(account, site)
       and account.json().get('status') == 'ok', synthetic_user=True, credentialed_simple_post=True)
  tokens = c.post('/api/login/oauth/access_token', data={'grant_type':'authorization_code',
      'client_id':app, 'client_secret':f['clients'][app], 'redirect_uri':p['redirectUri'],
      'code':result['data'], 'code_verifier':verifier}).json()
  jwks = c.get('/.well-known/jwks').json()
  claims = jwt.decode(tokens['id_token'], jwks, algorithms=['RS256'], audience=app,
      issuer=origin, access_token=tokens['access_token'])
  case('pkce_and_nonce_'+site, secrets.compare_digest(claims['nonce'], nonce))
  # Cookie-authenticated mutation must use the same trust decision as CORS.
  logout = c.post('/api/logout', data={'client_id':app,
      'post_logout_redirect_uri':f['callbacks'][app], 'state':p['state']})
  case('trusted_cookie_logout_'+site, logout.status_code in (200,302) and not cookie(c))
 with client() as c:
  wrong = c.post('/api/login', params=p, content=json.dumps({**body,'password':'synthetic-wrong-password'}),
      headers={'Origin':site, 'Content-Type':'text/plain;charset=UTF-8'})
  case('wrong_password_readable_'+site, readable(wrong, site) and wrong.json().get('status') == 'error')

for site in ('https://evil.example', 'https://evil.openlims.ai',
             'https://www.openlims.ai.evil.example', 'http://www.openlims.ai',
             'https://www.openlims.ai:8443', 'null'):
 with client() as c:
  for method in ('GET','OPTIONS'):
   response = c.request(method, '/api/get-account', headers={'Origin':site})
   case('untrusted_'+method+'_'+site, response.headers.get('access-control-allow-credentials') != 'true')
session, _ = login()
response = session.post('/api/sso-logout', params={'logoutAll':'true'}, headers={'Origin':'https://evil.example'})
case('untrusted_cookie_mutation_denied', response.status_code >= 400 or response.json().get('status') == 'error')
case('untrusted_logout_preserves_session', cookie(session))
print(json.dumps(rows))
assert all(row['passed'] for row in rows), 'Credentialed CORS regression failed'
'''

parser = argparse.ArgumentParser()
parser.add_argument('--image', default='mb-casd-v4:local')
parser.add_argument('--tools-image', default='mb-casd-iam-v4-tools:local')
parser.add_argument('--run-tag', required=True)
parser.add_argument('--default-off', action='store_true')
args = parser.parse_args()
assert re.fullmatch('[a-z0-9-]{1,8}', args.run_tag)
assert args.tools_image == 'mb-casd-iam-v4-tools:local' or re.fullmatch(r'sha256:[0-9a-f]{64}', args.tools_image)
image = resolve_candidate(args.image)
probe.r.TOOLS_IMAGE = args.tools_image
output = HERE / '.runs' / ('cors-' + args.run_tag)
output.parent.mkdir(exist_ok=True)
controller = PREFIX + CONTROLLER.replace("enabled = f['credentialed_origins_enabled']", 'enabled = ' + repr(not args.default_off))
try:
    probe.run_fixture('mdm-e2e-cors-' + args.run_tag, output, controller, image=image,
                      credentialed_origins=() if args.default_off else ORIGINS)
except Exception as error:
    print(json.dumps({'status':'failed', 'error_type':type(error).__name__, 'private_details_suppressed':True}))
    raise SystemExit(1) from None
finally:
    if output.exists():
        (output / 'test-inputs.json').write_text(json.dumps({'image':image,
            'controller_sha256':hashlib.sha256(controller.encode()).hexdigest(),
            'credentialed_origins':[] if args.default_off else ORIGINS,
            'browser_test':False}, indent=2))
