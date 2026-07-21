from __future__ import annotations
import json
from datetime import datetime,timezone,timedelta
from pathlib import Path
from ..storage import DATA_DIR

QUEUE=DATA_DIR/"pending-heartbeats.jsonl"

def _fresh(item:dict,max_age_hours:int)->bool:
 try:
  sent=datetime.fromisoformat(str(item.get("sent_at","")).replace("Z","+00:00"));sent=sent.replace(tzinfo=timezone.utc) if sent.tzinfo is None else sent
  return sent>=datetime.now(timezone.utc)-timedelta(hours=max_age_hours)
 except (TypeError,ValueError):return False

def enqueue(payload:dict,max_items:int=500,max_age_hours:int=24)->None:
 QUEUE.parent.mkdir(parents=True,exist_ok=True)
 if payload.get("sent_at") and any(item.get("sent_at")==payload["sent_at"] for item in pending(limit=500)):
  return
 items=[x for x in pending(limit=max_items) if _fresh(x,max_age_hours)];items.append(payload);items=items[-max_items:];temp=QUEUE.with_suffix(".tmp");temp.write_text("".join(json.dumps(x,ensure_ascii=False)+"\n" for x in items),encoding="utf-8");temp.replace(QUEUE)

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
