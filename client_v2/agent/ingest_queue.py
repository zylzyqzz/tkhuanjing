from __future__ import annotations
import json
from pathlib import Path
from ..storage import DATA_DIR

QUEUE=DATA_DIR/"pending-heartbeats.jsonl"

def enqueue(payload:dict)->None:
 QUEUE.parent.mkdir(parents=True,exist_ok=True)
 if payload.get("sent_at") and any(item.get("sent_at")==payload["sent_at"] for item in pending(limit=500)):
  return
 with QUEUE.open("a",encoding="utf-8") as f:f.write(json.dumps(payload,ensure_ascii=False)+"\n")

def pending(limit:int=100)->list[dict]:
 try:lines=QUEUE.read_text(encoding="utf-8").splitlines()
 except OSError:return []
 result=[]
 for line in lines[:limit]:
  try:result.append(json.loads(line))
  except ValueError:continue
 return result

def acknowledge(sent_at_values:set[str])->None:
 try:items=[json.loads(line) for line in QUEUE.read_text(encoding="utf-8").splitlines() if line.strip()]
 except (OSError,ValueError):return
 remaining=[x for x in items if x.get("sent_at") not in sent_at_values];temp=QUEUE.with_suffix(".tmp")
 temp.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in remaining),encoding="utf-8");temp.replace(QUEUE)
