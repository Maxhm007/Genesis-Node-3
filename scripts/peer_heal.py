#!/usr/bin/env python3
"""Quorum-based Genesis cross-node recovery coordinator."""
from __future__ import annotations
import json, os, re, subprocess, sys

PREFIX = "[genesis-peer-heal]"
VOTE_PREFIX = "peer_vote:"

def gh(endpoint: str, *, method: str = "GET", payload=None, allow_fail: bool = False):
    cmd = ["gh", "api", "--method", method, endpoint]; data = None
    if payload is not None:
        cmd += ["--input", "-"]; data = json.dumps(payload)
    proc = subprocess.run(cmd, input=data, text=True, capture_output=True)
    if proc.returncode:
        if allow_fail: return None
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    text = proc.stdout.strip(); return json.loads(text) if text else {}

def parse_body(body: str):
    out = {}
    for line in body.splitlines():
        if ":" in line:
            key, value = line.split(":", 1); key = key.strip()
            if key in {"source_node","source_repo","source_run_id","source_run_url"}: out[key] = value.strip()
    return out

def issue_comments(repo, number): return gh(f"repos/{repo}/issues/{number}/comments?per_page=100") or []
def comment(repo, number, body): gh(f"repos/{repo}/issues/{number}/comments", method="POST", payload={"body": body})
def close_issue(repo, number): gh(f"repos/{repo}/issues/{number}", method="PATCH", payload={"state": "closed"})
def latest_success(repo):
    runs = gh(f"repos/{repo}/actions/workflows/self-healing.yml/runs?per_page=5", allow_fail=True)
    if not runs: return False
    for run in runs.get("workflow_runs", []):
        if run.get("status") == "completed": return run.get("conclusion") == "success"
    return False

def coord_issue(repo, run_id, node):
    title = f"[genesis-network-repair] {node} run {run_id}"
    for item in gh(f"repos/{repo}/issues?state=open&per_page=100") or []:
        if item.get("title") == title: return int(item["number"])
    created = gh(f"repos/{repo}/issues", method="POST", payload={"title": title, "body": f"Genesis network repair coordination.\n\nsource_node: {node}\nsource_run_id: {run_id}\npolicy: self-heal first; peer recovery requires 2-of-3 quorum.\n"})
    return int(created["number"])
def voters(repo, number):
    result=set()
    for item in issue_comments(repo, number):
        m=re.search(r"peer_vote:\s*([A-Za-z0-9_.-]+)", item.get("body") or "")
        if m: result.add(m.group(1))
    return result
def dispatch(repo): return gh(f"repos/{repo}/actions/workflows/self-healing.yml/dispatches", method="POST", payload={"ref":"main"}, allow_fail=True) is not None

def main():
    if not (os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")):
        print("GENESIS_NETWORK_TOKEN missing; cross-node healing is disabled.", file=sys.stderr); return 1
    node=os.getenv("NODE_ID","genesis-node-unknown"); own=os.getenv("GITHUB_REPOSITORY") or os.getenv("NODE_REPO")
    if not own: return 1
    requests=[i for i in (gh(f"repos/{own}/issues?state=open&per_page=100") or []) if (i.get("title") or "").startswith(PREFIX)]
    if not requests: print("No peer recovery requests."); return 0
    for req in requests:
        meta=parse_body(req.get("body") or ""); repo=meta.get("source_repo"); run_id=meta.get("source_run_id","unknown"); source=meta.get("source_node","unknown"); number=int(req["number"])
        if not repo: comment(own,number,"Invalid recovery request: missing source_repo."); continue
        if latest_success(repo): comment(own,number,f"Recovery verified by {node}: target self-healing is healthy."); close_issue(own,number); continue
        coordination=coord_issue(repo,run_id,source); current=voters(repo,coordination)
        if node not in current: comment(repo,coordination,f"{VOTE_PREFIX} {node}\naction: approve conservative recovery")
        current=voters(repo,coordination); comment(own,number,f"{node} voted for recovery. quorum={len(current)}/2")
        if len(current)>=2:
            comment(own,number,"Quorum reached. Target self-healing dispatched; awaiting healthy verification." if dispatch(repo) else "Quorum reached, but target self-healing could not be dispatched. Escalation remains open.")
    return 0
if __name__ == "__main__": raise SystemExit(main())
