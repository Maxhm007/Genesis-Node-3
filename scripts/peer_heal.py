#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, subprocess
PREFIX='[genesis-peer-heal]'; VOTE_PREFIX='peer_vote:'

def gh(args,input_obj=None,allow_fail=False):
    cmd=['gh','api',*args]; data=None
    if input_obj is not None: cmd += ['--input','-']; data=json.dumps(input_obj)
    p=subprocess.run(cmd,input=data,text=True,capture_output=True)
    if p.returncode and not allow_fail: raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    if p.returncode: return None
    t=p.stdout.strip(); return json.loads(t) if t else {}

def parse_body(body):
    out={}
    for line in body.splitlines():
        if ':' in line:
            k,v=line.split(':',1); k=k.strip()
            if k in {'source_node','source_repo','source_run_id','source_run_url'}: out[k]=v.strip()
    return out

def comments(repo,n): return gh([f'repos/{repo}/issues/{n}/comments','-f','per_page=100']) or []
def comment(repo,n,body): gh([f'repos/{repo}/issues/{n}/comments'],{'body':body})
def close(repo,n): gh([f'repos/{repo}/issues/{n}'],{'state':'closed'})

def latest_success(repo):
    r=gh([f'repos/{repo}/actions/workflows/self-healing.yml/runs','-f','per_page=5'],allow_fail=True)
    if not r: return False
    for run in r.get('workflow_runs',[]):
        if run.get('status')=='completed': return run.get('conclusion')=='success'
    return False

def coord_issue(repo,run_id,node):
    title=f'[genesis-network-repair] {node} run {run_id}'
    for i in gh([f'repos/{repo}/issues','-f','state=open','-f','per_page=100']) or []:
        if i.get('title')==title: return int(i['number'])
    i=gh([f'repos/{repo}/issues'],{'title':title,'body':f'Genesis network repair coordination.\n\nsource_node: {node}\nsource_run_id: {run_id}\npolicy: self-heal first; peer recovery requires 2-of-3 quorum.\n'})
    return int(i['number'])

def voters(repo,n):
    out=set()
    for c in comments(repo,n):
        m=re.search(r'peer_vote:\s*([A-Za-z0-9_.-]+)',c.get('body') or '')
        if m: out.add(m.group(1))
    return out

def dispatch(repo): return gh(['--method','POST',f'repos/{repo}/actions/workflows/self-healing.yml/dispatches'],{'ref':'main'},allow_fail=True)

def main():
    if not (os.getenv('GH_TOKEN') or os.getenv('GITHUB_TOKEN')):
        print('GENESIS_NETWORK_TOKEN missing; peer healing skipped.'); return 0
    node=os.getenv('NODE_ID','genesis-node-3'); own=os.getenv('GITHUB_REPOSITORY') or os.getenv('NODE_REPO')
    if not own: return 1
    reqs=[i for i in (gh([f'repos/{own}/issues','-f','state=open','-f','per_page=100']) or []) if (i.get('title') or '').startswith(PREFIX)]
    for req in reqs:
        m=parse_body(req.get('body') or ''); repo=m.get('source_repo'); run_id=m.get('source_run_id','unknown'); source=m.get('source_node','unknown')
        if not repo: comment(own,req['number'],'Invalid recovery request: missing source_repo.'); continue
        if latest_success(repo): comment(own,req['number'],f'Recovery verified by {node}.'); close(own,req['number']); continue
        ci=coord_issue(repo,run_id,source); vs=voters(repo,ci)
        if node not in vs: comment(repo,ci,f'{VOTE_PREFIX} {node}\naction: approve conservative recovery')
        vs=voters(repo,ci); comment(own,req['number'],f'{node} voted for recovery. quorum={len(vs)}/2')
        if len(vs)>=2:
            if dispatch(repo) is None: comment(own,req['number'],'Quorum reached but target self-healing dispatch failed; escalation remains open.')
            else: comment(own,req['number'],'Quorum reached; target self-healing dispatched; awaiting verification.')
    return 0
if __name__=='__main__': raise SystemExit(main())
