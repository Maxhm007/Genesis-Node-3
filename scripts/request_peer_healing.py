#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys
PREFIX='[genesis-recovery-request]'

def gh(endpoint,method='GET',payload=None):
    cmd=['gh','api','--method',method,endpoint]; data=None
    if payload is not None: cmd += ['--input','-']; data=json.dumps(payload)
    p=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    t=p.stdout.strip(); return json.loads(t) if t else {}

def main():
    if not (os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')):
        print('Local GITHUB_TOKEN missing; cannot record recovery request.',file=sys.stderr); return 1
    node=os.getenv('NODE_ID','genesis-node-3'); repo=os.getenv('GITHUB_REPOSITORY','Maxhm007/Genesis-Node-3'); run_id=os.getenv('GITHUB_RUN_ID','unknown')
    title=f'{PREFIX} {node} {run_id}'
    body=(f'Genesis recovery request.\n\nsource_node: {node}\nsource_repo: {repo}\nsource_run_id: {run_id}\n'
          f'source_run_url: https://github.com/{repo}/actions/runs/{run_id}\nrequested_action: peer_validate_then_local_repair\n'
          'policy: self-heal-first; peer-heal-second; 2-of-3 quorum for peer recovery\n')
    issues=gh(f'repos/{repo}/issues?state=open&per_page=100')
    if isinstance(issues,list) and any(i.get('title')==title for i in issues): return 0
    gh(f'repos/{repo}/issues',method='POST',payload={'title':title,'body':body})
    return 0
if __name__=='__main__': raise SystemExit(main())
