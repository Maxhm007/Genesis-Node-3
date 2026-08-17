#!/usr/bin/env python3
from __future__ import annotations
import json, pathlib, subprocess, sys
CRITICAL=['node.json','GENE_REGISTRY.json','LEARNING_POLICY.json','attestation.json']

def valid(path):
    try: json.loads(pathlib.Path(path).read_text(encoding='utf-8')); return True
    except Exception: return False

def restore(path):
    p=subprocess.run(['git','show',f'HEAD^:{path}'],text=True,capture_output=True)
    if p.returncode: return False
    pathlib.Path(path).write_text(p.stdout,encoding='utf-8'); return valid(path)

def main():
    bad=[p for p in CRITICAL if not valid(p)]
    if not bad: print('Node health OK'); return 0
    failed=[p for p in bad if not restore(p)]
    if failed: print('Unable to restore: '+', '.join(failed),file=sys.stderr); return 1
    subprocess.run(['git','config','user.name','Genesis AI'],check=True)
    subprocess.run(['git','config','user.email','genesis-ai@users.noreply.github.com'],check=True)
    subprocess.run(['git','add',*bad],check=True)
    subprocess.run(['git','commit','-m','Self-heal critical node state'],check=True)
    subprocess.run(['git','push','origin','HEAD:main'],check=True)
    print('Local self-heal completed'); return 0
if __name__=='__main__': raise SystemExit(main())
