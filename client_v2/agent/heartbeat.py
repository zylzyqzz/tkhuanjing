from __future__ import annotations
from datetime import datetime,timezone
import os,time
import psutil
from ..api import ClientApi
from ..live_studio import live_studio_process_state
from ..product import APP_VERSION
from ..api import ApiError
from ..storage import clear_credentials,load_config,load_credentials
from .ingest_queue import acknowledge,enqueue,pending

ALLOWED_COMMANDS={"refresh_config","sync_binding"}

def payload()->dict:
 config=load_config();credentials=load_credentials();studio=live_studio_process_state()
 return {"device_id":config["device_id"],"binding_id":int(credentials["v2_binding_id"]) if credentials.get("v2_binding_id") else None,"agent_version":APP_VERSION,"sent_at":datetime.now(timezone.utc).isoformat(),"uptime_seconds":max(0,int(time.time()-psutil.boot_time())),"status":"online","live_software":{"name":"TikTok LIVE Studio","running":studio=="running"},"collection":{"status":"healthy","provider":"client_agent","last_success_at":datetime.now(timezone.utc).isoformat()},"metrics":{"cpu_percent":psutil.cpu_percent(interval=None),"memory_percent":psutil.virtual_memory().percent,"network_latency_ms":None,"upload_mbps":None}}

def flush_once()->dict:
 config=load_config();credentials=load_credentials();token=credentials.get("device_token","")
 if not token:return {"sent":0,"queued":0}
 api=ClientApi(config["api_base"],token);bootstrap={}
 try:
  bootstrap=api.v2_device_bootstrap()
 except ApiError as exc:
  if exc.code in {"AUTH_INVALID","AUTH_EXPIRED"} or exc.status_code==401:
   clear_credentials("device_token","v2_binding_id")
   return {"sent":0,"queued":len(pending()),"auth_error":exc.code or "AUTH_INVALID"}
  if exc.code in {"DEVICE_NOT_BOUND","AUTH_ORGANIZATION_REQUIRED"}:
   return {"sent":0,"queued":len(pending()),"unbound":True,"response":{}}
 except Exception:
  bootstrap={}
 runtime=bootstrap.get("config",{});heartbeat_enabled=bootstrap.get("features",{}).get("device_heartbeat",True)
 if not heartbeat_enabled:return {"sent":0,"queued":len(pending()),"response":{},"bootstrap":bootstrap}
 current=payload();enqueue(current,int(runtime.get("queue_max_items",500)),int(runtime.get("queue_max_age_hours",24)));sent=set();last={}
 for item in pending():
  try:
   last=api.v2_heartbeat(item)
   commands=[command.get("type","") if isinstance(command,dict) else str(command) for command in last.get("commands",[])]
   if any(command not in ALLOWED_COMMANDS for command in commands):raise RuntimeError("服务端返回了非白名单命令")
   sent.add(item["sent_at"])
  except ApiError as exc:
   if exc.code in {"AUTH_INVALID","AUTH_EXPIRED"} or exc.status_code==401:
    clear_credentials("device_token","v2_binding_id")
    return {"sent":len(sent),"queued":len(pending()),"response":last,"bootstrap":bootstrap,"auth_error":exc.code or "AUTH_INVALID"}
   break
  except Exception:break
 acknowledge(sent);result={"sent":len(sent),"queued":len(pending()),"response":last}
 if bootstrap:result["bootstrap"]=bootstrap
 return result
