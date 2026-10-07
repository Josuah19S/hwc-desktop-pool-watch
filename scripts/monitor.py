"""Observa el desktop pool en modo solo lectura y registra los cambios."""

import argparse
import json
import time
from datetime import datetime, timezone

from huaweicloudsdkcore.exceptions.exceptions import ClientRequestException, SdkException
from huaweicloudsdkworkspace.v2 import (
  ListDesktopPoolAuthorizedObjectsRequest,
  ListItaSubJobsRequest,
  ListPoolDesktopsDetailRequest,
  ShowDesktopPoolDetailRequest,
)

from common import ROOT, build_client, fail, find_pool_id, load_config

JOB_TYPES = ("createDesktops", "expandDesktopPool", "attachDesktopPool")
EMPTY = {"summary": {}, "desktops": {}, "authorized": [], "jobs": {}}


def take_snapshot(client, pool_id):
  """Toma una instantánea del pool usando solo llamadas de lectura."""
  pool = client.show_desktop_pool_detail(ShowDesktopPoolDetailRequest(pool_id=pool_id))
  total, used = pool.desktop_count or 0, pool.desktop_used or 0

  desktops = {}
  resp = client.list_pool_desktops_detail(ListPoolDesktopsDetailRequest(pool_id=pool_id, limit=100))
  for d in resp.pool_desktops or []:
    users = [u.user_name for u in d.attach_user_infos or []] or ([d.user_name] if d.user_name else [])
    desktops[d.desktop_id] = {"name": d.computer_name, "status": d.status,
                              "login": d.login_status, "user": ",".join(sorted(users))}

  resp = client.list_desktop_pool_authorized_objects(
    ListDesktopPoolAuthorizedObjectsRequest(pool_id=pool_id, limit=100))
  authorized = sorted(f"{o.object_type}:{o.object_name}" for o in resp.objects or [])

  # El SDK expone job_type como un solo valor: una consulta por tipo.
  jobs = {}
  for job_type in JOB_TYPES:
    resp = client.list_ita_sub_jobs(ListItaSubJobsRequest(job_type=job_type, limit=10))
    for j in resp.jobs or []:
      ent = j.entities
      jobs[j.id] = {"job_type": j.job_type, "status": j.status, "job_id": j.job_id,
                    "desktop": ent and (ent.desktop_name or ent.desktop_id),
                    "user": j.attach_user or (ent and ent.user_name)}

  return {"summary": {"total": total, "used": used, "idle": total - used},
          "desktops": desktops, "authorized": authorized, "jobs": jobs}


def diff(old, new):
  """Compara dos instantáneas y devuelve la lista de eventos (función pura)."""
  events = []
  if old["summary"] != new["summary"]:
    events.append({"type": "summary_changed", "old": old["summary"], "new": new["summary"]})

  for did, d in new["desktops"].items():
    prev = old["desktops"].get(did)
    if prev is None:
      events.append({"type": "desktop_added", "id": did, **d})
      continue
    for field in d:
      if d[field] != prev[field]:
        events.append({"type": "desktop_changed", "id": did, "name": d["name"],
                       "field": field, "old": prev[field], "new": d[field]})
  for did in old["desktops"].keys() - new["desktops"].keys():
    events.append({"type": "desktop_removed", "id": did, **old["desktops"][did]})

  for obj in sorted(set(new["authorized"]) - set(old["authorized"])):
    events.append({"type": "authorized_added", "object": obj})
  for obj in sorted(set(old["authorized"]) - set(new["authorized"])):
    events.append({"type": "authorized_removed", "object": obj})

  for jid, j in new["jobs"].items():
    prev = old["jobs"].get(jid)
    if prev is None or prev["status"] != j["status"]:
      events.append({"type": "job", "id": jid, **j})
  return events


def describe(ev):
  """Texto legible de un evento para la consola."""
  t = ev["type"]
  if t == "summary_changed":
    n = ev["new"]
    return f"Resumen: total={n['total']} usados={n['used']} idle={n['idle']}"
  if t in ("desktop_added", "desktop_removed"):
    verb = "nuevo" if t == "desktop_added" else "eliminado"
    return (f"Desktop {verb}: {ev['name']} ({ev['id']}) estado={ev['status']} "
            f"login={ev['login'] or '-'} usuario={ev['user'] or '-'}")
  if t == "desktop_changed":
    return f"Desktop {ev['name']}: {ev['field']} {ev['old'] or '-'} -> {ev['new'] or '-'}"
  if t.startswith("authorized_"):
    return f"Autorizado {'agregado' if t.endswith('added') else 'quitado'}: {ev['object']}"
  if t == "job":
    return (f"Job {ev['job_type']} {ev['status']}: desktop={ev['desktop'] or '-'} "
            f"usuario={ev['user'] or '-'} (sub-job {ev['id']})")
  return f"{t}: {ev.get('message', '')}"


def emit(log, ev):
  """Imprime el evento con hora local y lo agrega al log JSONL con hora UTC."""
  print(f"{datetime.now():%H:%M:%S}  {describe(ev)}")
  record = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), **ev}
  log.write(json.dumps(record, ensure_ascii=False) + "\n")
  log.flush()


def main():
  parser = argparse.ArgumentParser(description="Monitor de solo lectura de un desktop pool.")
  parser.add_argument("--once", action="store_true", help="toma una sola instantánea y termina")
  args = parser.parse_args()

  cfg = load_config()
  client = build_client(cfg)
  logs_dir = ROOT / "logs"
  logs_dir.mkdir(exist_ok=True)
  log_path = logs_dir / f"monitor-{datetime.now():%Y%m%d-%H%M%S}.jsonl"

  with open(log_path, "a", encoding="utf-8") as log:
    prev = None
    pool_id = None
    print(f"Pool '{cfg['pool_name']}', cada {cfg['poll_seconds']} s. Log: {log_path}")
    while True:
      try:
        pool_id = pool_id or find_pool_id(client, cfg["pool_name"])
        snap = take_snapshot(client, pool_id)
        if prev is None:
          print("--- Línea base ---")
        for ev in diff(prev or EMPTY, snap):
          emit(log, ev)
        prev = snap
      except ClientRequestException as e:
        if e.status_code in (401, 403):
          fail(f"autenticación/autorización rechazada ({e.status_code}): {e.error_msg}")
        emit(log, {"type": "error", "message": f"HTTP {e.status_code}: {e.error_msg}"})
      except SdkException as e:
        emit(log, {"type": "error", "message": f"{type(e).__name__}: {e}"})
      if args.once:
        break
      time.sleep(cfg["poll_seconds"])


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nMonitor detenido.")
