"""Owned, internal-only synthetic IAM fixture runtime; never accepts an existing database."""
import json,re,secrets,subprocess,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
TOOLS_ROOT=HERE
RUN=None
LABEL=None
OUT=None
STATE={}
SENSITIVE=[]
PG18='postgres@sha256:a02db8cac496f15b094798a38254f14d6e00741f709360e5e00bb6668ea31636'
TOOLS_IMAGE='mb-casd-iam-v4-tools:local'
def new_secret():
    value = secrets.token_hex(32)
    SENSITIVE.append(value)
    return value

def save():
    (OUT / 'runtime.json').write_text(json.dumps(STATE, indent=2))

def emit(stage, **fields):
    row = {'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'stage': stage, **fields}
    with (OUT / 'events.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False) + '\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)

def docker(*args, data=None, timeout=120, allow_failure=False):
    creation = args[:2] == ('run', '-d') or args[:2] == ('network', 'create')
    if creation:
        assert STATE['pending'] is None
        STATE['pending'] = args[args.index('--name') + 1] if args[0] == 'run' else args[-1]
        save()
    try:
        p = subprocess.run(['docker', *args], input=data, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Outcome uncertain; inspect owned ledger, do not repeat') from None
    if p.returncode and not allow_failure:
        diagnostic = (p.stdout + p.stderr).decode(errors='replace')
        for value in SENSITIVE:
            diagnostic = diagnostic.replace(value, '[redacted]')
        diagnostic = re.sub(r'eyJ[\w-]+\.[\w-]+\.[\w-]+', '[token-redacted]', diagnostic)
        with (OUT / 'command-errors.txt').open('a') as errors:
            errors.write(diagnostic[-5000:] + '\n')
        emit('command_failed', operation=args[0], exit_code=p.returncode, private_output_suppressed=True)
        raise RuntimeError('Owned test command failed')
    if creation and not p.returncode:
        if args[0] == 'run':
            STATE['containers'][STATE['pending']] = p.stdout.decode().strip()
        else:
            STATE['network'] = p.stdout.decode().strip()
        STATE['pending'] = None
        save()
    return p if allow_failure else p.stdout

def start(suffix, image, *args):
    return docker('run', '-d', '--name', RUN + '-' + suffix, '--network', RUN + '-net',
                  '--label', LABEL, *args, image).decode().strip()

def sql(pg, db, query):
    assert pg in {'pg16', 'pg18'} and re.fullmatch(r'[a-z0-9_]+', db)
    return docker('exec', '-i', RUN + '-' + pg, 'psql', '-X', '-U', 'cmab_app', '-d', db,
                  '-v', 'ON_ERROR_STOP=1', '-At', data=query.encode()).decode().strip()

def create_db(pg, db):
    docker('exec', RUN + '-' + pg, 'createdb', '-U', 'cmab_app', '-T', 'template0', db)

def tool(suffix, image, source, env):
    args = ['--mount', 'type=bind,source=' + str(source) + ',target=/code,readonly',
            '--tmpfs', '/tmp:rw', '--tmpfs', '/runtime:rw', '-w', '/code', '--entrypoint', 'sleep']
    for key, value in env.items():
        args.extend(['-e', key + '=' + value])
    # sleep is supplied after the image; Runtime helper deliberately keeps argv private.
    docker('run', '-d', '--name', RUN + '-' + suffix, '--network', RUN + '-net', '--label', LABEL,
           *args, image, 'infinity')

def iam(suffix, image, database, password, initial, *, dcr_self_logout=(), self_policy_clients=(), scoped_logout_clients=(), credentialed_origins=()):
    name = RUN + '-' + suffix
    docker('run', '-d', '--name', name, '--network', RUN + '-net', '--label', LABEL,
           '--tmpfs', '/runtime:rw,noexec,nosuid,mode=1777', '--tmpfs', '/conf:rw,noexec,nosuid,mode=1777', '--entrypoint', 'sh', image,
           '-c', 'while [ ! -f /runtime/ready ]; do sleep 1; done; exec /server')
    conf = (HERE / 'official-app.conf.template').read_text()
    settings = {'httpport': '8000', 'runmode': 'prod', 'driverName': 'postgres',
                'dataSourceName': json.dumps(f'user=cmab_app password={password} host={RUN}-pg18 port=5432 sslmode=disable dbname={database}'),
                'dbName': database, 'showSql': 'false', 'origin': '"http://localhost:19081"',
                'staticBaseUrl': '"http://localhost:19081"', 'socks5Proxy': '',
                'initDataFile': '"/runtime/init.json"', 'initDataNewOnly': 'true',
                'initAdminPassword': json.dumps(new_secret()),
                'logConfig': '{"adapter":"file","filename":"/runtime/iam.log","level":3,"maxdays":1}'}
    if credentialed_origins:
        assert set(credentialed_origins) == {'https://www.openlims.ai', 'https://pm.openlims.ai'}
        settings['credentialedOrigins'] = json.dumps(','.join(credentialed_origins))
    if dcr_self_logout:
        approved={'mdm-signing-login','mdm-signing-portal','mdm-signing-pm'}
        assert set(dcr_self_logout)==approved and len(dcr_self_logout)==3
        settings['dcrSelfLogoutApplications']=json.dumps(','.join('mdm-signing-synthetic/'+name for name in sorted(dcr_self_logout)))
    if self_policy_clients:
        assert set(self_policy_clients)=={'mdm-signing-pm','mdm-signing-portal'} and len(self_policy_clients)==2
        settings['openlimsSelfPolicyApplications']=json.dumps(','.join('mdm-signing-synthetic/'+name for name in sorted(self_policy_clients)))
    if scoped_logout_clients:
        assert set(scoped_logout_clients)=={'mdm-signing-login','mdm-signing-pm','mdm-signing-portal'} and len(scoped_logout_clients)==3
        settings['dcrSelfLogoutDeviceApplications']=json.dumps(','.join('mdm-signing-synthetic/'+name for name in sorted(scoped_logout_clients)))
        settings['openlimsScopedLogout']='true'
        settings['openlimsSelfPolicyDelegationBindings']=json.dumps('mdm-signing-synthetic/mdm-signing-pm=mdm-signing-synthetic/mdm-signing-pm-delegation')
    for key, value in settings.items():
        pattern = '^' + re.escape(key) + r'\s*=.*$'
        conf = re.sub(pattern, lambda _: key + ' = ' + value, conf, flags=re.M) if re.search(pattern, conf, re.M) else conf + '\n' + key + ' = ' + value + '\n'
    docker('exec', '-i', name, 'sh', '-c', 'umask 077; cat > /conf/app.conf', data=conf.encode())
    docker('exec', '-i', name, 'sh', '-c', 'umask 077; cat > /runtime/init.json', data=json.dumps(initial).encode())
    if dcr_self_logout:
        observed=docker('exec',name,'sh','-c',"grep '^dcrSelfLogoutApplications' /conf/app.conf").decode().strip()
        assert observed==('dcrSelfLogoutApplications = '+settings['dcrSelfLogoutApplications'])
        emit('approved_self_logout_setting_written',applications=list(sorted(dcr_self_logout)),self_policy_clients=list(self_policy_clients),scoped_logout_clients=list(scoped_logout_clients),no_organization_management=True)
    docker('exec', name, 'touch', '/runtime/ready')
    check = "import httpx; r=httpx.get('http://" + name + ":8000/.well-known/openid-configuration',headers={'Host':'localhost:19081'},trust_env=False,timeout=2);assert r.status_code==200"
    for _ in range(75):
        p = docker('exec', RUN + '-pm-tools', 'python', '-c', check, allow_failure=True)
        if p.returncode == 0:
            break
        state = json.loads(docker('inspect', '--format', '{{json .State}}', name))
        if not state.get('Running'):
            emit('iam_startup_failed',suffix=suffix,state=state.get('Status'),exit_code=state.get('ExitCode'))
            break
        time.sleep(.4)
    else:
        raise RuntimeError('Owned IAM not ready; no migration success claimed')
    if p.returncode:
        log = docker('logs','--tail','40',name,allow_failure=True)
        text = (log.stdout+log.stderr).decode(errors='replace')
        for secret in SENSITIVE:text=text.replace(secret,'[redacted]')
        text = '\n'.join(line for line in text.splitlines() if re.search(r'panic|error|fatal|failed',line,re.I))
        (OUT/(suffix+'-startup-diagnostic.txt')).write_text(text)
        raise RuntimeError('Owned IAM startup failed; sanitized error summary saved')
    emit('iam_ready', suffix=suffix, image=image, database=database)

def cleanup():
    if STATE['pending']:
        emit('cleanup_pending', uncertain_creation=STATE['pending'])
        return
    for name, identity in reversed(list(STATE['containers'].items())):
        observed = json.loads(docker('inspect', '--format', '{{json .Config.Labels}}', identity))
        assert observed.get('mdm.test.run') == RUN
        docker('stop', '--time', '5', identity)
        docker('rm', '-v', identity)
    if STATE['network']:
        network = json.loads(docker('network', 'inspect', STATE['network']))[0]
        assert network['Labels'].get('mdm.test.run') == RUN and not network['Containers']
        docker('network', 'rm', STATE['network'])
    remaining = docker('ps', '-aq', '--filter', 'label=' + LABEL).decode().splitlines()
    assert not remaining
    emit('cleaned', containers_removed=len(STATE['containers']), network_removed=bool(STATE['network']),
         remaining=[], tmpfs_credentials_and_archives_destroyed=True, published_ports=[])
