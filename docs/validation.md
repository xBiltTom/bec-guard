# Historial de validación de BEC Guard

Validación realizada el 20 de octubre de 2026 en Linux.

## Resultados

| Comprobación | Resultado |
| --- | --- |
| Backend: `pytest` | 3 pruebas aprobadas, sin advertencias tras usar httpx2. |
| Backend: Ruff check y format check | Aprobados. |
| Frontend: ESLint | Aprobado. |
| Frontend: Prettier check | Aprobado. |
| Frontend: TypeScript y build Vite | Aprobados. |
| `docker compose config --quiet` | Código de salida 0 con `.env` configurado. |
| `docker compose up --build -d --wait --wait-timeout 180` | Imágenes construidas; los cuatro servicios healthy. |
| FastAPI `/health` | HTTP 200 y contrato esperado, consultando PostgreSQL real. |
| Vite `/health` | HTTP 200 mediante proxy al backend real. |
| PostgreSQL | `SELECT 1` devuelve 1; ninguna tabla en `public`; tablas internas de n8n en su esquema. |
| n8n `/healthz/readiness` | HTTP 200, `{"status":"ok"}` al terminar su inicialización. |
| Chromium: flujo completo | React muestra “Backend conectado ✓” tras petición real a FastAPI y PostgreSQL. |
| Chromium: error y reintento | Un 503 simulado en la red del navegador muestra no disponible; al retirar la simulación el reintento vuelve a conectar con la API real. |
| Chromium: móvil | Sin desbordamiento horizontal a 375 px. |
| Chromium: n8n | Página de creación de propietario accesible; no se creó cuenta ni workflow. |
| Secretos | `.env` y variantes locales ignorados; permisos 600; `.env.example` sin secretos. |

La comprobación del navegador usó Playwright temporalmente en `/tmp`, sin añadirlo
como dependencia del repositorio. Las pruebas unitarias del backend sustituyen la
conexión SQLAlchemy; las comprobaciones de Compose y navegador usan PostgreSQL real.

## Particularidades del entorno

- El acceso a Docker, las descargas y TestClient requirieron ejecución fuera del
  sandbox. TestClient se bloqueaba dentro del entorno restringido; fuera de él
  pasó correctamente.
- El equipo ya usaba 5432 para otro PostgreSQL. Solo el `.env` local usa
  `POSTGRES_PORT=5433`; `.env.example` conserva el valor convencional 5432.
- n8n devolvió 503 durante la primera inicialización y después quedó healthy.
  Emite avisos propios sobre defaults futuros y su runner interno de código.
  No impiden usar el editor. No se añadió un servicio de runners porque esta
  fase no ejecuta workflows ni nodos de código.

Al cerrar Fase 1 no había modelos SQL del dominio. Autenticación de BEC Guard,
motor BEC, scoring, integraciones LLM, recepción real de correos, workflows de n8n
y dashboards siguen fuera del alcance actual.

## Minifase de consolidación entre Fase 1 y Fase 2

Se separaron en la documentación `AlertStatus` y `AlertVerdict`, conservando
`verdict = null` antes de una decisión humana, y se confirmó exactamente un rol
por usuario en el MVP. Las transiciones y permisos siguen pendientes de Fase 2.
La revisión de arquitectura y contratos no encontró referencias inconsistentes.

Se añadió `.github/workflows/ci.yml` con dos jobs independientes para pushes y
pull requests a `main`, sin secretos ni servicios de base de datos.

| Validación local de la minifase | Resultado |
| --- | --- |
| `uv sync --frozen` | Dependencias instaladas según el lockfile, sin modificarlo. |
| `uv run pytest` | 3 pruebas aprobadas, sin advertencias. |
| `uv run ruff check .` y `uv run ruff format --check .` | Aprobados. |
| `npm ci` | Instalación desde el lockfile, sin modificarlo. |
| `npm run lint`, `npm run format:check` y `npm run build` | Aprobados. |
| `actionlint` 1.7.12 | Workflow válido, sin errores. Herramienta temporal en `/tmp`. |
| Consistencia y alcance | AlertStatus contiene solo OPEN, UNDER_REVIEW y CLOSED; AlertVerdict contiene CONFIRMED_BEC y FALSE_POSITIVE. Sin cambios en aplicaciones ni infraestructura. |

La validación local usó Python 3.14 y Node.js 26, compatible con `package.json`;
CI selecciona Python 3.14 y Node.js 24. Se reutilizaron cachés locales en `/tmp`.
TestClient se ejecutó fuera del sandbox por la limitación ya documentada.
No se levantó Compose porque la infraestructura no cambió. El primer CI remoto
de esta minifase sí se ejecutó correctamente en GitHub: workflow `CI`, commit
`ee9f6e8a5f97f98e3f047328cd8ac3a43e3905d7`, resultado **success**.
En esa minifase todavía no se implementó Fase 2.

## Fase 2A: User y Alembic

Se trabajó en `main` desde `ee9f6e8`, con el árbol inicialmente limpio. Se añadió
solo User como modelo SQL, Role como enum Python con CHECK, Base común, sesiones
y la revisión `0001_create_users`. No se implementó Fase 2B.

### Migraciones ejecutadas realmente

En un PostgreSQL 18 temporal, separado de Compose, sin volúmenes de desarrollo y
sin n8n, se validó:

1. Base vacía, sin tablas del dominio.
2. `upgrade head`: existen `public.users` y `public.alembic_version`, revisión `0001_create_users`.
3. `downgrade base`: desaparece users y alembic_version queda vacía.
4. Nuevo `upgrade head`: users vuelve a crearse con sus constraints y timestamps con timezone.
5. `alembic check`: sin diferencias con la metadata.

La suite revierte esa base de pruebas a base al terminar. Nunca se hizo downgrade
en desarrollo. Allí se ejecutó únicamente `alembic upgrade head` mediante Settings
y `alembic check`, ambos correctos. Quedaron users y alembic_version, sin usuarios
de prueba insertados.

Se comparó la estructura de n8n antes y después: las mismas **160 tablas, 1270
columnas y 1429 constraints**, con nombres y definiciones idénticos. No se creó,
eliminó ni recreó su esquema.

### Pruebas y calidad

| Comprobación | Resultado |
| --- | --- |
| `uv sync --frozen` y comprobación de uv.lock | Correctos; solo se añadió Alembic y sus dependencias. |
| `pytest -v` con TEST_DATABASE_URL | **11 aprobadas**, sin omisiones ni advertencias: 3 unitarias y 8 de integración. |
| User en PostgreSQL | Commit real y lectura desde otra Session para los cuatro roles; UUID v4, email, is_active y timestamps UTC correctos. |
| Integridad | Email duplicado rechazado por uq_users_email; rol inválido rechazado por ck_users_role incluso mediante SQL directo. |
| Actualización | updated_at avanza, created_at se conserva y se puede cambiar is_active. |
| Ruff check y format check | Aprobados. |
| Frontend: lint, format:check y build | Aprobados, sin cambios en su código. |
| actionlint 1.7.12 | Workflow válido, sin errores. |
| Docker Compose config | Válido. |
| Imagen backend | Construida con Alembic, alembic.ini y migrations. |
| Alembic en Docker | upgrade head y check correctos desde la imagen nueva. |
| Servicios después del cambio | Los cuatro healthy; API y proxy responden el contrato de salud, n8n responde 200. |
| OpenAPI | Solo /health; sin endpoints de users o auth. |

CI conserva dos jobs independientes. Solo backend incorpora un service container
PostgreSQL 18 efímero con TEST_DATABASE_URL. Las fixtures ejecutan las migraciones
y su ciclo de reversión. No requiere secretos reales, `.env`, Compose ni n8n.
El workflow actualizado de Fase 2A aún no se ejecutó remotamente: no se hizo push.
Sus comandos y el equivalente PostgreSQL local sí se validaron.

TestClient y el acceso local a PostgreSQL se ejecutaron fuera del sandbox por las
restricciones del entorno. Node local fue 26 compatible; CI mantiene Node 24.
El servidor de pruebas solo utiliza trust en loopback y es descartable; desarrollo
conserva sus credenciales y volúmenes. Ver [persistencia](persistence.md) para repetir
las pruebas y conocer los límites de updated_at y normalización de email.
