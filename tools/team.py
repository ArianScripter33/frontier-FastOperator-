#!/usr/bin/env python3
"""Serialize explicit Git commits and mirror committed snapshots to OpenScion."""
import argparse
import fcntl
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

PREFIX = {'claude':'🎃 Claude', 'codex':'🔵 Codex', 'gemini':'🟢 Gemini'}
BIN = Path(os.environ.get('OPENSCION_BIN_DIR', '/Users/arianstoned/Developer/frontier-cdmx/.runtime/openscion-source/target/debug'))
ROOT = Path(__file__).resolve().parents[1]


def run(*args, capture=False, cwd=None, env=None):
    return subprocess.run(list(map(str,args)), cwd=cwd or ROOT, env=env,
                          check=True, stdout=subprocess.PIPE if capture else None).stdout


def git(*args):
    return run('git',*args,capture=True).decode().strip()


def allowed(path):
    p=Path(path)
    return not (p.is_absolute() or '..' in p.parts or any(x in {'.git','.venv','.runtime','.opnscn','__pycache__'} for x in p.parts)
                or p.name.startswith(('.env','memory')) or p.name in {'events.jsonl','credentials.json','secrets.json'}
                or p.suffix in {'.pem','.key','.log'})


def mirror_snapshot(sha, mirror):
    # Only Git-committed files cross into OpenScion; its scanner ignores no .gitignore.
    for p in mirror.iterdir():
        if p.name != '.opnscn':
            if p.is_dir() and not p.is_symlink(): shutil.rmtree(p)
            else: p.unlink()
    archive=run('git','archive',sha,capture=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tf:
        for member in tf.getmembers():
            if not allowed(member.name) or member.issym() or member.islnk():
                raise RuntimeError('Refusing unsafe committed path: '+member.name)
        tf.extractall(mirror)
    # Git archive timestamps have second precision; force a fresh stat so equal-size
    # edits in the same second cannot be skipped by OpenScion's metadata cache.
    for p in mirror.rglob('*'):
        if p.is_file() and '.opnscn' not in p.relative_to(mirror).parts:
            stamp=time.time_ns()
            os.utime(p,ns=(stamp,stamp))


def sync(meta):
    meta.mkdir(parents=True,exist_ok=True)
    endpoint_file=meta/'server.json'
    server=None
    if endpoint_file.exists():
        server=json.loads(endpoint_file.read_text())
        try:
            with urllib.request.urlopen(server['url']+'/healthz',timeout=1) as response:
                if response.read()!=b'ok': server=None
        except OSError: server=None
    if server is None:
        log=(meta/('server-'+str(time.time_ns())+'.log')).open('w')
        process=subprocess.Popen([str(BIN/'openscion-server'),'--listen','127.0.0.1:0'],
                                 stdout=log,stderr=log,start_new_session=True)
        log.close()
        log_path=Path(log.name)
        for _ in range(100):
            match=re.search(r'http://127\.0\.0\.1:\d+',log_path.read_text())
            if match: break
            if process.poll() is not None: raise RuntimeError('OpenScion server failed; see '+str(log_path))
            time.sleep(.05)
        else: raise RuntimeError('OpenScion server startup timed out')
        server={'url':match.group(), 'pid':process.pid, 'synced':[]}
        endpoint_file.write_text(json.dumps(server))
    mirror=meta/'mirror'
    mirror.mkdir(exist_ok=True)
    history=git('rev-list','--reverse','--first-parent','HEAD').splitlines()
    synced=server['synced']
    if history[:len(synced)]!=synced:
        raise RuntimeError('Git branch diverged from mirror; keep the integration branch linear')
    for sha in history[len(synced):]:
        mirror_snapshot(sha,mirror)
        subject=git('show','-s','--format=%s',sha)
        agent=next((a for a,p in PREFIX.items() if subject.startswith(p+': ')), 'codex')
        message=subject+' [git:'+sha+']'
        if not synced:
            shutil.rmtree(mirror/'.opnscn',ignore_errors=True)
            run(BIN/'opnscn','--server',server['url'],'import',mirror,'--author',agent,'-m',message)
        else:
            run(BIN/'opnscn','commit','--dir',mirror,'--author',agent,'-m',message)
        synced.append(sha)
        endpoint_file.write_text(json.dumps(server,indent=2)+'\n')
    print('OpenScion synchronized:',len(synced),'Git snapshots;',server['url'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    subs=parser.add_subparsers(dest='command',required=True)
    commit=subs.add_parser('commit')
    commit.add_argument('agent',choices=PREFIX)
    commit.add_argument('message')
    commit.add_argument('files',nargs='+')
    subs.add_parser('sync')
    subs.add_parser('status')
    args=parser.parse_args()
    meta=Path(git('rev-parse','--absolute-git-dir'))/'openscion'
    meta.mkdir(exist_ok=True)
    with (meta/'commit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if args.command=='status':
            print(git('status','--short'))
            print(git('log','-5','--format=%h %s'))
            print((meta/'server.json').read_text() if (meta/'server.json').exists() else 'OpenScion not synchronized')
            return
        if args.command=='commit':
            if not args.message.strip() or '\n' in args.message:
                raise RuntimeError('Use a nonempty, single-line subject')
            if git('diff','--cached','--name-only'):
                raise RuntimeError('Index already staged; review it before committing another agent work')
            for name in args.files:
                p=ROOT/name
                if not allowed(name) or p.is_dir() or p.is_symlink() or not p.resolve().is_relative_to(ROOT):
                    raise RuntimeError('Use explicit, safe, individual file paths: '+name)
            run('git','add','--',*args.files)
            staged=run('git','diff','--cached','--no-ext-diff',capture=True)
            if re.search(rb'(?:sk-or-v1-[A-Za-z0-9]{16,}|ftr_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)',staged):
                raise RuntimeError('Possible secret staged; commit refused, inspect index locally')
            names=git('diff','--cached','--name-only').splitlines()
            if not names or set(names)!=set(args.files):
                raise RuntimeError('Staged paths differ from requested paths; inspect index')
            env=dict(os.environ,SCION_AGENT=args.agent)
            run('git','commit','-m',PREFIX[args.agent]+': '+args.message,env=env)
        try:
            sync(meta)
        except Exception:
            print('Git history preserved; OpenScion synchronization incomplete. Retry: python3 tools/team.py sync',file=sys.stderr)
            raise


if __name__=='__main__':
    try: main()
    except (RuntimeError,subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
