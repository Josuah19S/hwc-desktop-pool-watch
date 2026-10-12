# Huawei Cloud - Desktop Pool Watch

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
| `HW_ENDPOINT` | No | Por defecto `https://workspace.la-south-2.myhuaweicloud.com` (LA-Santiago). |
| `HW_POOL_NAME` | No | Por defecto `dp-test`. |
| `POLL_SECONDS` | No | Intervalo de consulta. Por defecto `15`, mínimo `5`. |

Recomendación de seguridad: usa un usuario IAM de **solo lectura** para `monitor.py` y credenciales aparte para `expand.py`, que además necesita permisos sobre IMS, VPC y DSS.

## Uso

Los comandos se ejecutan desde la raíz del repositorio.

```bash
# Verificar credenciales y conectividad: una sola instantánea
python scripts/monitor.py --once

# Monitorear de forma continua (Ctrl+C para terminar)
python scripts/monitor.py

# Ver qué enviaría la expansión, sin ejecutarla
python scripts/expand.py --size 1 --dry-run

# Expandir (pide confirmación; --yes la omite)
python scripts/expand.py --size 1
```

`monitor.py` imprime primero la línea base y después solo los cambios: desktops nuevos o eliminados, cambios de estado, de sesión o de usuario asignado, cambios en el resumen del pool, usuarios autorizados agregados o quitados y jobs (`createDesktops`, `expandDesktopPool`, `attachDesktopPool`) nuevos o con estado distinto. Cada evento queda además en `logs/monitor-YYYYMMDD-HHMMSS.jsonl` (hora UTC). La carpeta `logs/` está en `.gitignore` porque puede contener nombres de usuario.

`expand.py` muestra el total de desktops antes y después. Según lo observado, `size` es la **cantidad de desktops a agregar**, no el tamaño total.

## Plan de prueba

Deja `monitor.py` corriendo durante toda la prueba.

1. El usuario A inicia sesión: queda con el desktop 1.
2. Se agrega el usuario B en la consola **sin** iniciar sesión: el total de desktops no debería cambiar.
3. B inicia sesión: observar si se crea un desktop y a quién se asigna.
4. B cierra sesión y vuelve a entrar: ¿mismo desktop?
5. Con A desconectado, B entra: ¿reutiliza el desktop de A?
6. Superar el máximo de desktops del pool (total, no solo autocreados): ¿qué mensaje recibe el usuario?

## Resultados observados

### Expansión manual (2026-10-07)

| Hora (UTC-05:00) | Fuente | Observación |
|---|---|---|
| 18:00 | `monitor.py` | Línea base: 1 desktop en total, 0 usados, 1 idle. El desktop está `ACTIVE`, sesión `REGISTERED`, sin usuario asignado. El pool tiene autorizado un grupo de usuarios. |
| ~18:01 | `expand.py --size 1` | Total antes: 1. Se crea un job con **un solo sub-job** (`RUNNING`). El script se interrumpió a los ~45 s; el job siguió ejecutándose en la nube. |
| 18:05 | `monitor.py` | 2 desktops en total, 0 usados, 2 idle. El desktop nuevo aparece sin estado y con sesión `UNREGISTER`, es decir, todavía en creación. |

- **Significado de `size` en `expand.py`:** `size` es la **cantidad de desktops a agregar por solicitud**, no el tamaño total. Confirmado en la consola de Workspace; con `size=1` el total pasó de 1 a 2.
- **Desktops creados por expansión:** quedan **sin usuario asignado** (idle) hasta que alguien inicia sesión.
- **Jobs en el monitor:** `monitor.py` no registró ningún job `expandDesktopPool`, aunque la expansión sí ocurrió. Falta revisar con qué `job_type` aparece ese sub-job en la API.
- **Pendiente:** ver cuánto tarda el desktop nuevo en pasar a `ACTIVE`/`REGISTERED`.

### Límite del pool

- La cantidad máxima es el **total de desktops del pool** (campo "desktop quantity" en la consola). Cuenta los desktops creados a mano, por `expand.py` y por inicio de sesión.
- `max_auto_created` (2 en `dp-test`) no es el límite efectivo: con 2 desktops en total, el pool no admite más. Para crecer hay que subir la cantidad en la consola.
- Configuración verificada por lectura en `dp-test`: `type` `STATIC`, `enable_autoscale` `True`, `autoscale_type` `ACCESS_CREATED`, `max_auto_created` 2. `once_auto_created` (1) está marcado como deprecado en el SDK.
- Mientras el pool está en el máximo, un inicio de sesión de un usuario sin desktop muestra **"No available cloud resources."** y no se crea nada.

### Plan de prueba (2026-10-07)

| Paso | Qué se probó | Resultado |
|---|---|---|
| 1 | A inicia sesión y queda con el desktop 1. | El usuario A se adjunta al desktop 1. |
| 2 | Se agrega B a la consola sin iniciar sesión: el total no debería cambiar. | Se mantiene la misma cantidad de desktops. |
| 3 | B inicia sesión. | Si hay un desktop libre (sin usuario), se le asigna a B. Si no hay ninguno y el pool no está en el máximo, se crea uno nuevo y queda asignado a B. |
| 4 | B cierra sesión y vuelve a entrar. | Recupera el mismo desktop. |
| 5 | Con A desconectado, B entra. | **No reutiliza** el desktop de A: B ya tenía el suyo, creado al iniciar sesión. |
| 6 | Se supera el máximo de desktops. | Sin desktop nuevo; el usuario ve "No available cloud resources.". |

### Incidencias

- **2026-10-12, 11:25 (UTC-05:00):** `monitor.py` falló con `HostUnreachableException`: no se pudo resolver `workspace.la-south-2.myhuaweicloud.com` (`getaddrinfo failed`). Al volver a resolver el host, responde. Es un fallo de DNS local, no de la API.

## Al terminar

**Elimina el pool** desde la consola. Los desktops pay-per-use siguen generando costo mientras existan.
