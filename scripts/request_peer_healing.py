#!/usr/bin/env python3
from __future__ import annotations
import json, os, subprocess, sys

def gh(args,payload=None):
    cmd=['gh','api',*args]; data=None
    if payload is not None: cmd += ['--input','-']; data=json.dumps(payload)
    p=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if p.returncode: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    t=p.stdout.strip(); return json.loads(t) if t else {}

def main():
    if not (os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')):
        print('GENESIS_NETWORK_TOKEN missing; peer recovery request skipped.'); return 0
    source_node=os.getenv('NODE_ID','genesis-node-3'); source_repo=os.getenv('GITHUB_REPOSITORY','Maxhm007/Genesis-Node-3'); run_id=os.getenv('GITHUB_RUN_ID','unknown')
    peers=[p.strip() for p in os.getenv('PEER_REPOS','').split(',') if p.strip()]
    title=f'[genesis-peer-heal] {source_node} recovery request {run_id}'
    body=f'Genesis peer recovery request.\n\nsource_node: {source_node}\nsource_repo: {source_repo}\nsource_run_id: {run_id}\nsource_run_url: https://github.com/{source_repo}/actions/runs/{run_id}\nrequested_action: diagnose_and_repair\npolicy: self-heal-first; peer-heal-second; risky repair requires peer quorum\n'
    ok=0
    for repo in peers:
        try:
            existing=gh([f'repos/{repo}/issues','-f','state=open','-f','per_page=100'])
            if isinstance(existing,list) and any(i.get('title')==title for i in existing): ok+=1; continue
            gh([f'repos/{repo}/issues'],{'title':title,'body':body}); ok+=1
        except Exception as e: print(f'peer request failed for {repo}: {e}',file=sys.stderr)
    return 0 if ok else 1
if __name__=='__main__': raise SystemExit(main())
