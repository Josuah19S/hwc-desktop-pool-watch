"""
common.py
Configuración, cliente del SDK y búsqueda del pool, compartidos por los scripts.
python scripts/common.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkworkspace.v2 import ListDesktopPoolsRequest, WorkspaceClient

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENDPOINT = "https://workspace.la-south-2.myhuaweicloud.com"  # Verificado para LA-Santiago


def fail(msg):
  """Termina el programa sin traza."""
  print(f"ERROR: {msg}", file=sys.stderr)
  sys.exit(1)


def load_config():
  """Lee y valida las variables de entorno (y .env si existe)."""
  env_file = ROOT / ".env"
  if env_file.exists():
    load_dotenv(env_file)

  missing = [k for k in ("HW_AK", "HW_SK", "HW_PROJECT_ID") if not os.getenv(k)]
  if missing:
    fail(f"faltan variables obligatorias: {', '.join(missing)}. "
         "Copia .env.example a .env y complétalo.")

  try:
    poll = int(os.getenv("POLL_SECONDS", "15"))
  except ValueError:
    fail("POLL_SECONDS debe ser un número entero.")

  return {
    "ak": os.environ["HW_AK"],
    "sk": os.environ["HW_SK"],
    "project_id": os.environ["HW_PROJECT_ID"],
    "endpoint": os.getenv("HW_ENDPOINT") or DEFAULT_ENDPOINT,
    "pool_name": os.getenv("HW_POOL_NAME") or "dp-test",
    "poll_seconds": max(poll, 5),
  }


def build_client(cfg):
  """Crea el WorkspaceClient con endpoint explícito (la región puede no estar en el SDK)."""
  credentials = BasicCredentials(cfg["ak"], cfg["sk"], cfg["project_id"])
  return (WorkspaceClient.new_builder()
          .with_credentials(credentials)
          .with_endpoint(cfg["endpoint"])
          .build())


def find_pool_id(client, name):
  """Devuelve el ID del pool cuyo nombre coincide exactamente con `name`."""
  resp = client.list_desktop_pools(ListDesktopPoolsRequest(name=name, limit=100))
  matches = [p.id for p in resp.desktop_pools or [] if p.name == name]
  if not matches:
    fail(f"no se encontró un pool con nombre exacto '{name}'.")
  if len(matches) > 1:
    fail(f"hay {len(matches)} pools con nombre '{name}'; usa un nombre único.")
  return matches[0]
