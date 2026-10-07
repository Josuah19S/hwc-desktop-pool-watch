# hwc-desktop-pool-watch

Scripts para observar cómo se comporta un **Desktop Pool estático** de Huawei Cloud Workspace cuando se agregan usuarios y cuando inician sesión por primera vez: ¿se expande el pool?, ¿cuándo se crea el desktop?, ¿a quién queda asignado y si esa asignación es permanente?

> **Proyecto no oficial.** No tiene relación con Huawei ni cuenta con su respaldo.

- `scripts/monitor.py`: observa el pool en modo **solo lectura** y registra los cambios.
- `scripts/expand.py`: expande el pool manualmente, para comparar con la escala automática.

## Requisitos e instalación

- Python 3.10 o superior.
- Un pool de tipo `STATIC` ya creado en la consola (por defecto `dp-test`), con la política de escalado "Creation upon access".

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración

Copia `.env.example` a `.env` y completa los valores:

| Variable | Obligatoria | Descripción |
|---|---|---|
| `HW_AK`, `HW_SK` | Sí | Credenciales de acceso. Nunca se imprimen. |
| `HW_PROJECT_ID` | Sí | ID del proyecto de la región `la-south-2`. |
| `HW_ENDPOINT` | No | Por defecto `https://workspace.la-south-2.myhuaweicloud.com` (no verificado). |
| `HW_POOL_NAME` | No | Por defecto `dp-test`. |
| `POLL_SECONDS` | No | Intervalo de consulta. Por defecto `15`, mínimo `5`. |

Recomendación de seguridad: usa un usuario IAM de **solo lectura** para `monitor.py` y credenciales aparte para `expand.py`, que además necesita permisos sobre IMS, VPC y DSS.

## Uso

Los comandos se ejecutan desde la carpeta `scripts/`.

```bash
cd scripts

# Verificar credenciales y conectividad: una sola instantánea
python monitor.py --once

# Monitorear de forma continua (Ctrl+C para terminar)
python monitor.py

# Ver qué enviaría la expansión, sin ejecutarla
python expand.py --size 1 --dry-run

# Expandir (pide confirmación; --yes la omite)
python expand.py --size 1
```

`monitor.py` imprime primero la línea base y después solo los cambios: desktops nuevos o eliminados, cambios de estado, de sesión o de usuario asignado, cambios en el resumen del pool, usuarios autorizados agregados o quitados y jobs (`createDesktops`, `expandDesktopPool`, `attachDesktopPool`) nuevos o con estado distinto. Cada evento queda además en `logs/monitor-YYYYMMDD-HHMMSS.jsonl` (hora UTC). La carpeta `logs/` está en `.gitignore` porque puede contener nombres de usuario.

`expand.py` muestra el total de desktops antes y después. **No se sabe aún** si `size` es la cantidad a agregar o el tamaño total resultante; ver "Resultados observados".

## Plan de prueba

Deja `monitor.py` corriendo durante toda la prueba.

1. El usuario A inicia sesión: queda con el desktop 1.
2. Se agrega el usuario B en la consola **sin** iniciar sesión: el total de desktops no debería cambiar.
3. B inicia sesión: observar si se crea un desktop y a quién se asigna.
4. B cierra sesión y vuelve a entrar: ¿mismo desktop?
5. Con A desconectado, B entra: ¿reutiliza el desktop de A?
6. Superar el máximo de autocreados: ¿qué mensaje recibe el usuario?

## Al terminar

**Elimina el pool** desde la consola. Los desktops pay-per-use siguen generando costo mientras existan.
