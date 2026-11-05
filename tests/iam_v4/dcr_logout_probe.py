"""Normal OAuth DCR/logout protocol regression. No UI, role expansion or server use."""

import json

from pathlib import Path

import time

import fixture_runtime as r

CONTROLLER = r'''
import base64,hashlib,json,secrets,time
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
import httpx
from jose import jwt
f=json.loads(Path('/runtime/fixture.json').read_text())
base=f['base']; origin='http://localhost:19081';org='mdm-signing-synthetic'
rows=[]
def case(name,passed,**fields):
 rows.append({'case':name,'passed':bool(passed),'kind':'real-http-not-browser','time_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**fields})
 Path('/runtime/results.json').write_text(json.dumps(rows,indent=2))
def client():return httpx.Client(base_url=base,headers={'Host':'localhost:19081'},trust_env=False,timeout=10,follow_redirects=False)
def login(name='signer',app='mdm-signing-login',session=None):
 c=session or client();verifier=secrets.token_urlsafe(48);nonce=secrets.token_urlsafe(24)
 challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
 p={'clientId':app,'responseType':'code','redirectUri':f['callbacks'][app],'scope':'openid profile','state':secrets.token_urlsafe(24),'nonce':nonce,'code_challenge':challenge,'code_challenge_method':'S256'}
 c.get('/login/oauth/authorize',params={'client_id':app,'redirect_uri':p['redirectUri'],'response_type':'code',**{k:v for k,v in p.items() if k not in ('clientId','redirectUri','responseType')}})
 b=c.post('/api/login',params=p,json={'type':'code','application':app,'organization':org,'signinMethod':'Password','username':'e2e.'+name,'password':f['users'][name]}).json()
 if isinstance(b.get('data'),dict) and b['data'].get('required') is True:
  b=c.post('/api/grant-consent',json={'application':'admin/'+app,'clientId':app,'grantedScopes':['openid','profile'],'scope':p['scope'],'signinMethod':'Password','responseType':'code','redirectUri':p['redirectUri'],'state':p['state'],'nonce':nonce,'challenge':challenge}).json()
 assert b.get('status')=='ok' and isinstance(b.get('data'),str),'Synthetic standard login/consent failed'
 tokens=c.post('/api/login/oauth/access_token',data={'grant_type':'authorization_code','client_id':app,'client_secret':f['clients'][app],'redirect_uri':p['redirectUri'],'code':b['data'],'code_verifier':verifier}).json()
 jwks=c.get('/.well-known/jwks').json()
 claims=jwt.decode(tokens['id_token'],jwks,algorithms=['RS256'],audience=app,issuer=origin,access_token=tokens['access_token'])
 assert secrets.compare_digest(claims['nonce'],nonce)
 return c,tokens
def cookie(c):
 b=c.get('/api/get-account').json();return b.get('status')=='ok' and isinstance(b.get('data'),dict)
def active(token):
 with client() as c:return c.get('/api/userinfo',headers={'Authorization':'Bearer '+token}).status_code==200
a,ta=login();b,tb=login(app='mdm-signing-pm');other,to=login('other')
with client() as c:
 denial=c.post('/api/sso-logout',params={'logoutAll':'true'},headers={'Authorization':'Bearer '+ta['access_token']})
 business=denial.json().get('status')
case('dcr_bearer_all_logout_denied',business=='error' and cookie(a) and cookie(b),http=denial.status_code,business_status=business,client_tags_preserved=True)
info=a.get('/api/userinfo',headers={'Authorization':'Bearer '+ta['access_token']}).json()
case('v4_userinfo_not_full_e074_policy',all(k not in info for k in ('needUpdatePassword','lastChangePasswordTime')) and isinstance(info.get('roles'),list),password_policy_fields_present=False,role_element_types=sorted({type(x).__name__ for x in info.get('roles',[])}))
state=secrets.token_urlsafe(32);target='http://localhost:19090/mdm/login'
rp=a.post('/api/logout',data={'client_id':'mdm-signing-login','post_logout_redirect_uri':target,'state':state})
location=rp.headers.get('location','');parsed=urlsplit(location)
rp_ok=rp.status_code==302 and (parsed.scheme+'://'+parsed.netloc+parsed.path)==target and parse_qs(parsed.query).get('state')==[state]
case('official_rp_current_session',rp_ok and not cookie(a) and cookie(b) and cookie(other),http=rp.status_code,state_preserved=rp_ok,other_device_cookie_still_active=cookie(b),not_all_device_logout=True,no_token_in_redirect='token' not in parsed.query)
all_response=b.post('/api/sso-logout',params={'logoutAll':'true'})
case('official_cookie_all_device_logout',all_response.json().get('status')=='ok' and not cookie(b) and not active(tb['access_token']) and cookie(other),http=all_response.status_code,other_user_preserved=cookie(other),frontend_workflow_implemented=False)
# Re-login normally, then self-change password via the documented API only.
u,tu=login();device,td=login(app='mdm-signing-pm');old=f['users']['signer'];new=secrets.token_hex(32)
wrong=u.post('/api/set-password',data={'userOwner':org,'userName':'e2e.signer','oldPassword':'synthetic-deliberately-wrong','newPassword':new}).json()
case('wrong_old_password_preserves_sessions',wrong.get('status')=='error' and cookie(u) and cookie(device),business_status=wrong.get('status'))
changed=u.post('/api/set-password',data={'userOwner':org,'userName':'e2e.signer','oldPassword':old,'newPassword':new}).json()
ok=changed.get('status')=='ok';f['users']['signer']=new
fresh,tf=login()
case('v7_password_change_revokes_old_cookie_and_tokens',ok and not cookie(u) and not cookie(device) and not active(tu['access_token']) and not active(td['access_token']) and cookie(fresh) and cookie(other),business_status=changed.get('status'),new_password_standard_login=True,other_user_preserved=cookie(other),ui_password_change_tested=False)
print(json.dumps(rows))
assert all(x['passed'] for x in rows),'Some protocol regressions failed'
'''

def run_fixture(run_id, output_dir, controller, *, image=None, self_logout_clients=(), fault_checks=False, self_policy_clients=(), scoped_logout_clients=(), refresh_clients=(), replica=False):
    """Shared fixture only; every client remains DCR and all data is synthetic."""
    assert set(refresh_clients) <= {'mdm-signing-pm'}, 'Only the approved synthetic PM refresh client'
    assert __import__('re').fullmatch(r'mdm-e2e-[a-z0-9-]{1,64}', run_id), 'Synthetic run ID required'
    assert Path(output_dir).resolve().parent == Path(__file__).resolve().parent / '.runs', 'Only owned ignored output is accepted'
    if image is None:
        raise ValueError('Use the CLI to bind the reviewed local image before fixture creation')
    r.RUN = run_id
    r.LABEL = 'mdm.test.run=' + r.RUN
    r.OUT = Path(output_dir)
    r.STATE = {'run':r.RUN,'containers':{},'network':None,'pending':None}
    assert not r.OUT.exists(), 'Never overwrite a prior run'
    r.OUT.mkdir();r.save()
    pw=r.new_secret()
    try:
        r.docker('network','create','--internal','--label',r.LABEL,r.RUN+'-net')
        r.start('pg18',r.PG18,'--tmpfs','/var/lib/postgresql:rw','-e','POSTGRES_USER=cmab_app','-e','POSTGRES_PASSWORD='+pw)
        for _ in range(60):
            if r.docker('exec',r.RUN+'-pg18','pg_isready','-U','cmab_app',allow_failure=True).returncode==0:break
            time.sleep(.3)
        else:raise RuntimeError('New pg18 unavailable')
        r.create_db('pg18','dcr_synthetic')
        r.tool('pm-tools',r.TOOLS_IMAGE,r.TOOLS_ROOT,{'APP_SECRET':r.new_secret()})
        clients={name:r.new_secret() for name in ('mdm-signing-login','mdm-signing-proof','mdm-signing-pm','mdm-signing-portal','mdm-signing-pm-delegation')}
        callbacks={'mdm-signing-login':'http://localhost:19090/mdm/api/v1/auth/oidc/callback','mdm-signing-proof':'http://localhost:19090/mdm/signature-callback','mdm-signing-pm':'http://localhost:19091/api/v1/auth/callback','mdm-signing-portal':'http://localhost:19092/api/v1/portal/callback','mdm-signing-pm-delegation':'http://localhost:19090/mdm/api/v1/auth/oidc/pm-callback'}
        users={name:r.new_secret() for name in ('signer','other')}
        apps=[]
        for name,secret in clients.items():
            home='http://localhost:19091' if name=='mdm-signing-pm' else 'http://localhost:19092' if name=='mdm-signing-portal' else 'http://localhost:19090/mdm'
            apps.append({'owner':'admin','name':name,'organization':'mdm-signing-synthetic','displayName':'Synthetic '+name,'cert':'synthetic-cert','homepageUrl':home,'enablePassword':True,'enableSignUp':False,'clientId':name,'clientSecret':secret,'tags':['dcr'],'grantTypes':['authorization_code'],'redirectUris':[callbacks[name],home+'/login'],'tokenFormat':'JWT','tokenFields':[],'expireInHours':1,'cookieExpireInHours':1,'enableSigninSession':True,'enableAutoSignin':True,'signinMethods':[{'name':'Password','displayName':'Password','rule':'All'}]})
            if name in refresh_clients:
                apps[-1]['grantTypes'].append('refresh_token')
        initial={'organizations':[{'owner':'admin','name':'mdm-signing-synthetic','displayName':'Synthetic DCR regression','passwordType':'bcrypt','languages':['en'],'isProfilePublic':False}],
                 'applications':apps,'users':[{'owner':'mdm-signing-synthetic','name':'e2e.'+n,'id':'synthetic-'+n,'type':'normal-user','password':p,'displayName':'Synthetic '+n,'tag':'dcr','isAdmin':False,'signupApplication':'mdm-signing-portal'} for n,p in users.items()],
                 'roles':[{'owner':'mdm-signing-synthetic','name':role,'isEnabled':True,'users':['mdm-signing-synthetic/e2e.'+n]} for role,n in [('cmc_lead','signer'),('rd','other')]],
                 'certs':[{'owner':'admin','name':'synthetic-cert','scope':'JWT','type':'x509','cryptoAlgorithm':'RS256','bitSize':2048,'expireInYears':1}]}
        r.iam('idp',image,'dcr_synthetic',pw,initial,dcr_self_logout=self_logout_clients,self_policy_clients=self_policy_clients,scoped_logout_clients=scoped_logout_clients)
        fixture={'base':'http://'+r.RUN+'-idp:8000','clients':clients,'callbacks':callbacks,'users':users}
        if replica:
            r.iam('idp2',image,'dcr_synthetic',pw,initial,dcr_self_logout=self_logout_clients,self_policy_clients=self_policy_clients,scoped_logout_clients=scoped_logout_clients)
            fixture['base_secondary']='http://'+r.RUN+'-idp2:8000'
        if fault_checks:
            fixture.update({'db_host':r.RUN+'-pg18','db_password':pw})
        r.docker('exec','-i',r.RUN+'-pm-tools','sh','-c','umask 077; cat > /runtime/fixture.json',data=json.dumps(fixture).encode())
        classification=json.loads(r.sql('pg18','dcr_synthetic',"SELECT json_agg(json_build_object('name',name,'tags',tags) ORDER BY name) FROM application WHERE name LIKE 'mdm-signing-%'"))
        assert len(classification)==5 and all(json.loads(x['tags'])==['dcr'] for x in classification)
        (r.OUT/'client-classification.json').write_text(json.dumps(classification,indent=2))
        output=r.docker('exec','-i',r.RUN+'-pm-tools','python','-',data=controller.encode(),timeout=100)
        rows=json.loads(output)
        (r.OUT/'protocol-results.json').write_text(json.dumps(rows,indent=2))
        r.emit('protocol_complete',passed=sum(x['passed'] for x in rows),cases=len(rows),real_browser=False)
    finally:
        if r.STATE['pending'] is None and r.RUN+'-pm-tools' in r.STATE['containers']:
            result=r.docker('exec',r.RUN+'-pm-tools','cat','/runtime/results.json',allow_failure=True)
            if result.returncode==0:
                (r.OUT/'protocol-results.json').write_text(json.dumps(json.loads(result.stdout),indent=2))
        r.cleanup()
