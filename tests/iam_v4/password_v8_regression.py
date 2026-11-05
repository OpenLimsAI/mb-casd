"""Reusable scenario assertions on the caller-specified fixed candidate."""
import dcr_logout_probe as probe
from dcr_product_review import PREFIX

tail=probe.CONTROLLER.split('# Re-login normally, then self-change password via the documented API only.')[1]

controller=PREFIX+'''
other,to=login('other')
default,td=login()
with client() as c:
 response=c.post('/api/sso-logout',params={'logoutAll':'true'},headers={'Authorization':'Bearer '+td['access_token']})
case('v8_default_configuration_keeps_dcr_self_logout_disabled',response.json().get('status')=='error' and cookie(default) and cookie(other))
'''+tail
