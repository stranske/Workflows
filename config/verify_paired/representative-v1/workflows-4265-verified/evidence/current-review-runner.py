from pathlib import Path
import subprocess,json,hashlib,datetime,sys,difflib
ROOT=Path('/tmp/real-verify-4265-current-review-verification-20261027-final')
ROOT.mkdir(exist_ok=False)
SNAP=ROOT/'snapshot';SNAP.mkdir()
TMP=ROOT/'fixtures';TMP.mkdir()
HOME=ROOT/'empty-home';HOME.mkdir()
SRC=Path('/Users/teacher/Library/CloudStorage/Dropbox/Learning/Code/Workflows')
HEAD='40622701645e1c9c13ff28861ba606a3f78d2e4a'
PYTHON='/opt/anaconda3/bin/python3'
sha=lambda b:hashlib.sha256(b).hexdigest()
files=['tools/coverage_guard.py','tests/test_coverage_guard.py']
blobs={}
for name in files:
    data=subprocess.check_output(['git','-C',str(SRC),'show',HEAD+':'+name])
    path=SNAP/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    blobs[name]={'sha256':sha(data),'git_blob':subprocess.check_output(['git','-C',str(SRC),'rev-parse',HEAD+':'+name]).decode().strip()}
(ROOT/'sandbox.sb').write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (subpath "'+str(ROOT.resolve())+'"))\n(deny file-read* (subpath "/Users/teacher"))\n')
env={'PATH':'/usr/bin:/bin','HOME':str(HOME),'TMPDIR':str(TMP),'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONDONTWRITEBYTECODE':'1','LANG':'en_US.UTF-8'}
receipt={'schema':'current-review-original-acceptance-procedure/v1','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'repository':'stranske/Workflows','pr':4265,'issue':4254,'original_pr_head':HEAD,'meaning':'Current reviewer execution of existing exact-head acceptance tests and deliberate break/revert; not evidence of what the PR author historically ran.','source_files':blobs,'environment':env,'kernel_sandbox_profile':(ROOT/'sandbox.sb').read_text(),'runs':[],'provider_calls':0}
def run(name,argv):
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    result=subprocess.run(argv,cwd=SNAP,env=env,capture_output=True,timeout=90)
    (ROOT/(name+'.stdout')).write_bytes(result.stdout)
    (ROOT/(name+'.stderr')).write_bytes(result.stderr)
    row={'name':name,'argv':argv,'cwd':str(SNAP),'started_utc':started,'exit_code':result.returncode,'stdout_sha256':sha(result.stdout),'stderr_sha256':sha(result.stderr)}
    receipt['runs'].append(row)
    (ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(row),flush=True)
    return result
prefix=['/usr/bin/sandbox-exec','-f',str(ROOT/'sandbox.sb'),PYTHON,'-I','-B']
probe=run('sandbox-and-runtime-probe',prefix+['-c','import sys,platform,socket,json; print(json.dumps({"executable":sys.executable,"version":sys.version,"platform":platform.platform()}));\ntry: socket.socket().connect(("127.0.0.1", 9))\nexcept PermissionError as e: print("KERNEL_NETWORK_DENIED",type(e).__name__)\nelse: raise SystemExit("network sandbox unexpectedly permitted loopback connection")'])
if probe.returncode:
    receipt['blocked']='Kernel network-denial/runtime probe failed; no pytest or mutation execution.'
    (ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    raise SystemExit(0)
names=['test_recovery_window_counts_records_accumulated_across_runs','test_recovery_message_names_records_held_and_needed']
def pytest_cmd(label,selected):
    args=['--log-file',str(ROOT/(label+'.pytest.log')),'--junitxml',str(ROOT/(label+'.junit.xml')),'-q','-o','addopts=','-c','/dev/null','--rootdir',str(SNAP),'--confcutdir',str(SNAP),'--basetemp',str(TMP/label),'-p','no:cacheprovider']+[str(SNAP/'tests/test_coverage_guard.py')+'::'+n for n in selected]
    code='import sys;sys.path.insert(0,'+repr(str(SNAP))+');import pytest;raise SystemExit(pytest.main('+repr(args)+'))'
    return prefix+['-c',code]
baseline=run('original-two-named-tests',pytest_cmd('original',names))
if baseline.returncode:
    receipt['blocked']='Original selected tests did not pass; deliberate break not attempted.'
else:
    module=SNAP/'tools/coverage_guard.py';original=module.read_bytes()
    old=b'for record in [*(previous if isinstance(previous, list) else []), sample]:'
    new=b'for record in [*(previous if isinstance(previous, list) else [])]:'
    if original.count(old)!=1:raise RuntimeError('Mutation anchor not unique')
    broken=original.replace(old,new)
    (ROOT/'mutation.patch').write_text(''.join(difflib.unified_diff(original.decode().splitlines(True),broken.decode().splitlines(True),fromfile='original/tools/coverage_guard.py',tofile='broken/tools/coverage_guard.py')))
    receipt['mutation']={'operation':'Remove only the current sample from existing accumulation iteration; retain all prior-history processing and test source unchanged.','before_sha256':sha(original),'broken_sha256':sha(broken),'patch_sha256':sha((ROOT/'mutation.patch').read_bytes())}
    try:
        module.write_bytes(broken)
        run('removed-current-append',pytest_cmd('broken',[names[0]]))
    finally:
        module.write_bytes(original)
        receipt['restored_sha256']=sha(module.read_bytes())
    run('restored-two-named-tests',pytest_cmd('restored',names))
receipt['final_source_files']={name:sha((SNAP/name).read_bytes()) for name in files}
receipt['interpreter_file_sha256']=sha(Path(PYTHON).resolve().read_bytes())
(ROOT/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(str(ROOT/'receipt.json'))
