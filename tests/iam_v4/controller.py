"""Appended to the standard synthetic OAuth helper inside owned tmpfs only."""
import concurrent.futures
import threading
import psycopg

PM = 'mdm-signing-pm'
db = psycopg.connect(host=f['db_host'], dbname='dcr_synthetic', user='cmab_app', password=f['db_password'])
db.autocommit = True

def sql(statement, params=()):
    with db.cursor() as cursor:
        cursor.execute(statement, params)
        return cursor.fetchone() if cursor.description else None

def begin(app=PM, name='signer', exchange=True):
    c = client(); c.timeout = 30
    proof = secrets.token_urlsafe(48); nonce = secrets.token_urlsafe(24)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(proof.encode()).digest()).rstrip(b'=').decode()
    p = {'clientId':app, 'responseType':'code', 'redirectUri':f['callbacks'][app],
         'scope':'openid profile', 'state':secrets.token_urlsafe(24), 'nonce':nonce,
         'code_challenge':challenge, 'code_challenge_method':'S256'}
    c.get('/login/oauth/authorize', params={'client_id':app, 'redirect_uri':p['redirectUri'],
          'response_type':'code', **{k:v for k,v in p.items() if k not in ('clientId','redirectUri','responseType')}})
    result = c.post('/api/login', params=p, json={'type':'code', 'application':app,
         'organization':org, 'signinMethod':'Password', 'username':'e2e.'+name, 'password':f['users'][name]}).json()
    if isinstance(result.get('data'), dict) and result['data'].get('required') is True:
        result = c.post('/api/grant-consent', json={'application':'admin/'+app, 'clientId':app,
          'grantedScopes':['openid','profile'], 'scope':p['scope'], 'signinMethod':'Password',
          'responseType':'code', 'redirectUri':p['redirectUri'], 'state':p['state'],
          'nonce':nonce, 'challenge':challenge}).json()
    assert result.get('status')=='ok' and isinstance(result.get('data'), str), 'Synthetic standard login failed'
    pending = (app, p['redirectUri'], proof, result['data'], nonce)
    if not exchange:
        return c, pending
    token = exchange_code(pending)
    assert token.get('access_token'), 'Synthetic code exchange failed'
    return c, token

def validate(tokens, app=PM, nonce=None):
    with client() as c:
        keys = c.get('/.well-known/jwks').json()
    claims = jwt.decode(tokens['id_token'], keys, algorithms=['RS256'], audience=app,
                        issuer=origin, access_token=tokens['access_token'])
    if nonce is not None:
        assert secrets.compare_digest(claims['nonce'], nonce)
    return claims

def token_client(node=None):
    if node is None:
        return client()
    assert node=='replica' and 'base_secondary' in f
    return httpx.Client(base_url=f['base_secondary'], headers={'Host':'localhost:19081'},
                        trust_env=False, timeout=30, follow_redirects=False)

def exchange_code(pending, *, proof=None, node=None):
    app, redirect, verifier, code, nonce = pending
    with token_client(node) as c:
        result = c.post('/api/login/oauth/access_token', data={'grant_type':'authorization_code',
            'client_id':app, 'client_secret':f['clients'][app], 'redirect_uri':redirect,
            'code':code, 'code_verifier':verifier if proof is None else proof}).json()
    if result.get('access_token'):
        validate(result, app, nonce)
    return result

def introspect(token):
    with client() as c:
        return c.post('/api/login/oauth/introspect', auth=(PM, f['clients'][PM]),
                      data={'token':token, 'token_type_hint':'access_token'}).json().get('active') is True

def userinfo_observation(token):
    with client() as c:
        response = c.get('/api/userinfo', headers={'Authorization':'Bearer '+token})
    try:
        body = response.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    nested = body.get('data')
    identity = bool(body.get('sub')) or (isinstance(nested, dict)
                  and any(k in nested for k in ('id','name','username','owner')))
    rejected = response.status_code>=400 or body.get('status')=='error' or bool(body.get('error'))
    return {'http':response.status_code, 'business_status':body.get('status'),
            'identity_returned':identity, 'explicit_rejection':bool(rejected)}

def refresh(tokens, *, app=PM, endpoint='/api/login/oauth/access_token', node=None):
    with token_client(node) as c:
        result = c.post(endpoint, data={'grant_type':'refresh_token',
           'client_id':app, 'client_secret':f['clients'][app], 'refresh_token':tokens['refresh_token']}).json()
    if result.get('access_token'):
        validate(result, app)
    return result

def change(c, *, wrong=False):
    value = secrets.token_hex(32)
    body = c.post('/api/set-password', data={'userOwner':org, 'userName':'e2e.signer',
        'oldPassword':'synthetic-deliberately-wrong' if wrong else f['users']['signer'], 'newPassword':value}).json()
    if not wrong:
        f['users']['signer'] = value  # Prove actual commit through the next normal password login.
    return body

def fault(enabled):
    sql('DROP TRIGGER IF EXISTS local_v10_fault ON public.token; DROP FUNCTION IF EXISTS local_v10_fault()')
    if enabled:
        sql("""CREATE FUNCTION local_v10_fault() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'synthetic token expiry update unavailable'; END $$;
        CREATE TRIGGER local_v10_fault BEFORE UPDATE OF expires_in ON public.token
        FOR EACH STATEMENT EXECUTE FUNCTION local_v10_fault();""")

def rotation_fault(mode=None):
    sql('DROP TRIGGER IF EXISTS local_v10_rotation_fault ON public.token; DROP FUNCTION IF EXISTS local_v10_rotation_fault()')
    if mode is None:
        return
    assert mode in ('insert','delete','commit')
    sql("""CREATE FUNCTION local_v10_rotation_fault() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'synthetic refresh persistence failure'; END $$;""")
    if mode=='commit':
        sql("""CREATE CONSTRAINT TRIGGER local_v10_rotation_fault AFTER DELETE ON public.token
        DEFERRABLE INITIALLY DEFERRED FOR EACH ROW WHEN (OLD.\"user\"='e2e.signer')
        EXECUTE FUNCTION local_v10_rotation_fault();""")
    else:
        operation = 'INSERT' if mode=='insert' else 'DELETE'
        record = 'NEW' if mode=='insert' else 'OLD'
        sql(f"""CREATE TRIGGER local_v10_rotation_fault BEFORE {operation} ON public.token
        FOR EACH ROW WHEN ({record}.\"user\"='e2e.signer') EXECUTE FUNCTION local_v10_rotation_fault();""")

def token_rows():
    return sql('SELECT count(*) FROM public.token WHERE "user"=%s AND application=%s', ('e2e.signer',PM))[0]

def gate(mode):
    sql('SELECT pg_advisory_lock(741260)')
    operation = 'UPDATE OF code_is_used' if mode=='code' else 'INSERT'
    condition = "OLD.\"user\"='e2e.signer' AND NOT OLD.code_is_used AND NEW.code_is_used" if mode=='code' else "NEW.\"user\"='e2e.signer'"
    sql(f"""CREATE FUNCTION local_v10_gate() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN PERFORM pg_advisory_xact_lock(741260); RETURN NEW; END $$;
    CREATE TRIGGER local_v10_gate BEFORE {operation} ON public.token FOR EACH ROW
    WHEN ({condition}) EXECUTE FUNCTION local_v10_gate();""")

def release():
    sql('SELECT pg_advisory_unlock(741260)')

def ungate():
    release()
    sql('DROP TRIGGER IF EXISTS local_v10_gate ON public.token; DROP FUNCTION IF EXISTS local_v10_gate()')

def wait_gate(count=1, *, second_code=False):
    for _ in range(180):
        advisory = sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event='advisory' AND pid<>pg_backend_pid()")[0]
        row_waiters = sql("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event IN ('transactionid','tuple') AND pid<>pg_backend_pid()")[0]
        if advisory >= count and (not second_code or row_waiters >= 1):
            return {'advisory_waiters':advisory, 'row_waiters':row_waiters}
        time.sleep(.05)
    raise RuntimeError('Controlled real request barrier not reached')

try:
    classification = sql("SELECT json_agg(json_build_object('name',name,'tags',tags,'grant_types',grant_types) ORDER BY name) FROM application WHERE organization=%s", (org,))[0]
    decoded = lambda value: json.loads(value) if isinstance(value, str) else value
    case('five_dcr_clients_only_pm_has_refresh_grant', len(classification)==5
         and all(decoded(item['tags'])==['dcr'] for item in classification)
         and all(decoded(item['grant_types'])==(['authorization_code','refresh_token'] if item['name']==PM else ['authorization_code']) for item in classification),
         clients=5, organization_admin_granted=False, published_ports=0)
    other, other_tokens = begin(name='other')
    a, tokens = begin(); b, second_tokens = begin(app='mdm-signing-portal')
    wrong = change(a, wrong=True)
    case('wrong_password_preserves_both_devices', wrong.get('status')=='error' and cookie(a) and cookie(b) and introspect(tokens['access_token']))
    pending_client, pending = begin(exchange=False)
    changed = change(a)
    fresh, current = begin()
    old_code = exchange_code(pending)
    old_refresh = refresh(tokens)
    case('password_change_revokes_cookie_access_refresh_pending_code', changed.get('status')=='ok'
         and not cookie(a) and not cookie(b) and not introspect(tokens['access_token'])
         and not introspect(second_tokens['access_token']) and not old_code.get('access_token')
         and not old_refresh.get('access_token') and cookie(fresh) and cookie(other),
         other_user_preserved=cookie(other), new_password_standard_login=True)

    _, pending = begin(exchange=False)
    incorrect = exchange_code(pending, proof=secrets.token_urlsafe(48))
    correct = exchange_code(pending)
    repeated = exchange_code(pending)
    case('pkce_failure_does_not_consume_code_then_replay_denied', not incorrect.get('access_token')
         and bool(correct.get('access_token')) and not repeated.get('access_token'))

    c, original = begin()
    rotated = refresh(original)
    assert rotated.get('access_token'), 'Refresh not supported by the explicitly configured synthetic PM client'
    first_claims, rotated_claims = validate(original), validate(rotated)
    reused = refresh(original)
    wrong_client = refresh(rotated, app='mdm-signing-portal')
    case('normal_refresh_keeps_verified_subject_audience_sid', bool(first_claims.get('sid'))
         and first_claims['sid']==rotated_claims.get('sid') and first_claims['sub']==rotated_claims['sub']
         and first_claims['aud']==rotated_claims['aud'] and introspect(rotated['access_token']))
    case('sequential_refresh_reuse_and_wrong_client_denied', not reused.get('access_token') and not wrong_client.get('access_token'))
    alternate = refresh(rotated, endpoint='/api/login/oauth/refresh_token')
    case('enabled_client_refreshes_through_alternate_endpoint', bool(alternate.get('access_token'))
         and validate(alternate).get('sid')==rotated_claims.get('sid'))

    # The alternate official endpoint must enforce the same explicit grant list.
    _, no_grant = begin(app='mdm-signing-login')
    denied_standard = refresh(no_grant, app='mdm-signing-login')
    denied_alternate = refresh(no_grant, app='mdm-signing-login', endpoint='/api/login/oauth/refresh_token')
    case('alternate_refresh_endpoint_does_not_bypass_grant_list', not denied_standard.get('access_token')
         and not denied_alternate.get('access_token'),
         standard_issued=bool(denied_standard.get('access_token')),
         alternate_issued=bool(denied_alternate.get('access_token')))

    c, original = begin(); _, pending = begin(exchange=False)
    fault(True)
    mutation = change(c)
    old_active = introspect(original['access_token'])
    info_denied = not active(original['access_token'])
    old_code = exchange_code(pending); renewed = refresh(original)
    fresh, _ = begin()
    case('token_expiry_store_failure_fails_closed', mutation.get('status')=='error' and cookie(fresh)
         and not cookie(c) and not old_active and info_denied and not old_code.get('access_token')
         and not renewed.get('access_token') and cookie(other),
         password_committed=True, revocation_api_reports_incomplete=mutation.get('status')=='error',
         old_access_active=old_active, other_user_preserved=cookie(other), atomicity_proven=False)
    fault(False)

    actor, old = begin(); _, pending = begin(exchange=False)
    renamed = False
    try:
        sql('ALTER TABLE public.token RENAME TO local_v10_token_unavailable')
        renamed = True
        mutation = change(actor)
        old_active = introspect(old['access_token'])
        info = userinfo_observation(old['access_token'])
        info_denied = info['explicit_rejection'] and not info['identity_returned']
        denied_code = exchange_code(pending); denied_refresh = refresh(old)
    finally:
        if renamed:
            sql('ALTER TABLE public.local_v10_token_unavailable RENAME TO token')
    fresh, _ = begin()
    case('token_store_read_outage_after_password_commit_fails_closed', mutation.get('status')=='error'
         and not old_active and info_denied and not denied_code.get('access_token')
         and not denied_refresh.get('access_token') and not cookie(actor) and cookie(fresh)
         and not introspect(old['access_token']) and cookie(other),
         password_committed=True, new_password_login_after_restore=True,
         mutation_business_status=mutation.get('status'), old_access_active_during_outage=old_active,
         userinfo_denied_during_outage=info_denied,
         userinfo=info,
         code_returned_during_outage=bool(denied_code.get('access_token')),
         refresh_returned_during_outage=bool(denied_refresh.get('access_token')),
         old_cookie_active_after_restore=cookie(actor),
         stale_access_still_denied_after_restore=not introspect(old['access_token']),
         other_user_preserved_after_restore=cookie(other))

    for mode in ('code','refresh'):
        actor, old = begin()
        if mode=='code': _, pending = begin(exchange=False)
        gate(mode); fault(True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            node = 'replica' if 'base_secondary' in f else None
            future = pool.submit(exchange_code, pending, node=node) if mode=='code' else pool.submit(refresh, old, node=node)
            try:
                observed = wait_gate()
                mutation = change(actor)
            finally:
                release()
            payload = future.result(timeout=35)
        ungate(); fault(False)
        fresh, _ = begin()
        returned = bool(payload.get('access_token'))
        case(mode+'_exchange_blocked_across_password_commit', mutation.get('status')=='error'
             and cookie(fresh) and not returned and payload.get('error')=='invalid_grant' and cookie(other),
             barrier=observed, password_committed=True, token_returned=returned,
             oauth_error=payload.get('error'), other_user_preserved=cookie(other), atomic_http_response_guaranteed=False,
             changed_on_primary_exchanged_on_replica='base_secondary' in f)

    for mode in ('insert','delete','commit'):
        _, original = begin()
        before = token_rows()
        rotation_fault(mode)
        failed = refresh(original)
        rotation_fault()
        after = token_rows()
        retained = introspect(original['access_token'])
        retry = refresh(original)
        case('refresh_'+mode+'_failure_has_no_orphan_and_is_retryable', not failed.get('access_token')
             and before==after and retained and bool(retry.get('access_token')),
             token_returned=bool(failed.get('access_token')), net_token_row_change=after-before,
             original_row_retained=retained, clean_retry_succeeds=bool(retry.get('access_token')))

    # Deterministically put two genuine requests at the same consume/insert boundary.
    for mode in ('code','refresh'):
        _, old = begin()
        if mode=='code': _, pending = begin(exchange=False)
        before = token_rows()
        gate(mode)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            nodes = [None, 'replica' if 'base_secondary' in f else None]
            futures = [pool.submit(exchange_code, pending, node=node) if mode=='code' else pool.submit(refresh, old, node=node) for node in nodes]
            try:
                observed = wait_gate(1 if mode=='code' else 2, second_code=mode=='code')
            finally:
                release()
            payloads = [future.result(timeout=35) for future in futures]
        ungate()
        issued = [p for p in payloads if p.get('access_token')]
        count_active = sum(introspect(p['access_token']) for p in issued)
        case('concurrent_same_'+mode+'_consumed_once', len(issued)==1 and count_active==1,
             successful_responses=len(issued), active_returned_tokens=count_active, barrier=observed,
             net_token_row_change=token_rows()-before, two_idp_processes='base_secondary' in f)

    case('other_user_remains_valid_after_all_faults_and_races', cookie(other) and introspect(other_tokens['access_token']))
    print(json.dumps(rows))
    assert all(row['passed'] for row in rows), 'Security contract regression failed; inspect safe case records'
finally:
    ungate(); fault(False); rotation_fault()
    db.close()
