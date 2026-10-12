"""
expand.py
Expande manualmente el desktop pool (genera costo).
python scripts/expand.py --size <num_desktops>
"""

import argparse
import time

from huaweicloudsdkcore.exceptions.exceptions import ClientRequestException, SdkException
from huaweicloudsdkworkspace.v2 import (
  ExpandDesktopPoolReq,
  ExpandDesktopPoolRequest,
  ListItaSubJobsRequest,
  ShowDesktopPoolDetailRequest,
)

from common import build_client, fail, find_pool_id, load_config

TIMEOUT_SECONDS = 600
PENDING = ("WAITING", "RUNNING")


def pool_total(client, pool_id):
  return client.show_desktop_pool_detail(ShowDesktopPoolDetailRequest(pool_id=pool_id)).desktop_count


def wait_job(client, job_id, poll_seconds):
  """Consulta los sub-jobs del job hasta que ninguno esté pendiente o se agote el tiempo."""
  deadline = time.monotonic() + TIMEOUT_SECONDS
  while time.monotonic() < deadline:
    jobs = client.list_ita_sub_jobs(ListItaSubJobsRequest(job_id=job_id, limit=100)).jobs or []
    counts = {}
    for j in jobs:
      counts[j.status] = counts.get(j.status, 0) + 1
    print(f"  sub-jobs: {counts or 'aún ninguno'}")
    if jobs and not any(j.status in PENDING for j in jobs):
      for j in jobs:
        if j.status != "SUCCESS":
          print(f"  sub-job {j.id} {j.status}: {j.fail_reason or j.error_code or '-'}")
      return True
    time.sleep(poll_seconds)
  return False


def main():
  parser = argparse.ArgumentParser(description="Expande el desktop pool (genera costo).")
  parser.add_argument("--size", type=int, required=True,
                      help="valor 'size' enviado a la API (cantidad a agregar)")
  parser.add_argument("--dry-run", action="store_true", help="muestra lo que enviaría, sin expandir")
  parser.add_argument("--yes", action="store_true", help="no pide confirmación")
  args = parser.parse_args()
  if args.size < 1:
    parser.error("--size debe ser mayor que 0")

  cfg = load_config()
  client = build_client(cfg)
  try:
    pool_id = find_pool_id(client, cfg["pool_name"])
    before = pool_total(client, pool_id)
    print(f"Pool '{cfg['pool_name']}': {before} desktops en total.")
    print(f"Se enviaría: POST /v2/{{project_id}}/desktop-pools/{{pool_id}}/expand  {{\"size\": {args.size}}}")
    if args.dry_run:
      print("--dry-run: no se llamó a la API de expansión.")
      return
    if not args.yes:
      answer = input("Esto crea desktops que generan costo. ¿Continuar? [s/N] ")
      if answer.strip().lower() != "s":
        print("Cancelado.")
        return

    body = ExpandDesktopPoolReq(size=args.size)
    job_id = client.expand_desktop_pool(ExpandDesktopPoolRequest(pool_id=pool_id, body=body)).job_id
    print(f"job_id: {job_id}")

    if not wait_job(client, job_id, cfg["poll_seconds"]):
      print(f"El job no terminó en {TIMEOUT_SECONDS // 60} minutos.")
    print(f"Total de desktops: antes={before}, después={pool_total(client, pool_id)}")
  except ClientRequestException as e:
    fail(f"la API rechazó la petición (HTTP {e.status_code}): {e.error_msg}")
  except SdkException as e:
    fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
  try:
    main()
  except KeyboardInterrupt:
    print("\nInterrumpido. Si ya se envió la expansión, el job sigue en la nube; revísalo con monitor.py.")
