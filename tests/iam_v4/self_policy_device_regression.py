"""Reusable scenario assertions on the caller-specified fixed candidate."""
from dcr_product_review import PREFIX

CONTROLLER=PREFIX+r'''
for app in f['clients']:
 c,t=login(app=app)
 with client() as read:
  info=read.get('/api/userinfo',headers={'Authorization':'Bearer '+t['access_token']}).json()
 p=info.get('openlims_self_policy')
 expected=app in ('mdm-signing-pm','mdm-signing-portal')
 case(app+'_fixed_own_policy',isinstance(p,dict)==expected,enabled=expected)
 if expected:
  case(app+'_exact_fields',set(p)=={'id','owner','isForbidden','isDeleted','needUpdatePassword','lastChangePasswordTime','roles'} and p['id']==info['sub'] and p['owner']==org and all(set(x)=={'owner','name','isEnabled'} for x in p['roles']),password_or_membership_returned=False)
  with client() as read:
   targeted=read.get('/api/userinfo',params={'userId':'e2e.other'},headers={'Authorization':'Bearer '+t['access_token']})
   basic=read.get('/api/userinfo',auth=(app,f['clients'][app]))
   users=read.get('/api/get-users',params={'owner':org},headers={'Authorization':'Bearer '+t['access_token']})
  case(app+'_target_basic_and_org_read_not_granted','openlims_self_policy' not in targeted.json() and 'openlims_self_policy' not in basic.json() and users.json().get('status')=='error')
a,ta=login(app='mdm-signing-pm');b,tb=login(app='mdm-signing-portal');other,to=login('other')
case('two_devices_and_other_user_before',cookie(a) and cookie(b) and cookie(other))
with client() as request:
 result=request.post('/api/sso-logout',params={'logoutAll':'false'},headers={'Authorization':'Bearer '+ta['access_token']})
case('own_token_current_device_only',result.json().get('status')=='ok' and not cookie(a) and not active(ta['access_token']) and cookie(b) and active(tb['access_token']) and cookie(other),http=result.status_code,other_device_preserved=cookie(b),other_user_preserved=cookie(other))
with client() as request:
 repeated=request.post('/api/sso-logout',params={'logoutAll':'false'},headers={'Authorization':'Bearer '+ta['access_token']})
 targeted=request.post('/api/sso-logout',params={'logoutAll':'false','sessionId':'untrusted-target'},headers={'Authorization':'Bearer '+tb['access_token']})
case('repeat_and_arbitrary_session_denied',repeated.json().get('status')=='error' and targeted.json().get('status')=='error' and cookie(b) and cookie(other))
fresh,tf=login(app='mdm-signing-login')
with client() as request:
 result=request.post('/api/sso-logout',params={'logoutAll':'true'},headers={'Authorization':'Bearer '+tb['access_token']})
case('all_devices_retained',result.json().get('status')=='ok' and not cookie(b) and not cookie(fresh) and not active(tb['access_token']) and not active(tf['access_token']) and cookie(other) and active(to['access_token']),other_user_preserved=cookie(other))
sid_device,sid_tokens=login(app='mdm-signing-pm')
claims=jwt.decode(sid_tokens['id_token'],sid_device.get('/.well-known/jwks').json(),algorithms=['RS256'],audience='mdm-signing-pm',issuer=origin,access_token=sid_tokens['access_token'])
case('verified_id_token_has_original_session_proof',isinstance(claims.get('sid'),str) and bool(claims['sid']),sid_value_not_recorded=True)
delegated,delegated_tokens=login(app='mdm-signing-pm-delegation')
with client() as resource:
 checked=resource.post('/api/login/oauth/introspect',auth=('mdm-signing-pm',f['clients']['mdm-signing-pm']),data={'token':delegated_tokens['access_token'],'token_type_hint':'access_token'}).json()
case('pm_resource_reads_only_current_delegated_user_policy',checked.get('active') is True and isinstance(checked.get('openlims_self_policy'),dict),delegate_client_itself_not_granted=True)
with client() as resource:
 denied=resource.post('/api/login/oauth/introspect',auth=('mdm-signing-portal',f['clients']['mdm-signing-portal']),data={'token':delegated_tokens['access_token'],'token_type_hint':'access_token'}).json()
 targeted=resource.post('/api/login/oauth/introspect',auth=('mdm-signing-pm',f['clients']['mdm-signing-pm']),data={'token':delegated_tokens['access_token'],'token_type_hint':'access_token','userId':'e2e.other'}).json()
case('portal_cannot_read_delegation_and_target_field_denied','openlims_self_policy' not in denied and 'openlims_self_policy' not in targeted)

print(json.dumps(rows));assert all(x['passed'] for x in rows)
'''
