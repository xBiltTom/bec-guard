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

Al cerrar Fase 1 no había modelos SQL del dominio ni autenticación. Motor BEC,
scoring, integraciones LLM, recepción real de correos, workflows de n8n y dashboards
siguen fuera del alcance actual.

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
El CI remoto de Fase 2A sobre `7ff605a86a617b0ead97c00abf3702a593538c6a`
terminó en **SUCCESS** en GitHub. Sus comandos y el equivalente PostgreSQL local
también se validaron.

TestClient y el acceso local a PostgreSQL se ejecutaron fuera del sandbox por las
restricciones del entorno. Node local fue 26 compatible; CI mantiene Node 24.
El servidor de pruebas solo utiliza trust en loopback y es descartable; desarrollo
conserva sus credenciales y volúmenes. Ver [persistencia](persistence.md) para repetir
las pruebas y conocer los límites de updated_at y normalización de email.

## Fase 2B: autenticación, RBAC y auditoría

Se partió de main limpio en `7ff605a`. Se validaron incrementalmente 2B.1
(identidad, passwords y bootstrap), 2B.2 (login/JWT/me), 2B.3 (RBAC) y 2B.4
(auditoría). No se hizo push ni se implementó Fase 3.

| Comprobación final | Resultado |
| --- | --- |
| Suite backend con PostgreSQL 18 real | **59 pruebas aprobadas**, sin omisiones: 17 unitarias y 42 de integración. |
| Identidad | trim/lowercase, duplicados por casing rechazados incluso por SQL directo, colisiones de migración abortadas sin fusionar ni avanzar versión. |
| Passwords/bootstrap | Argon2id, verificación correcta/incorrecta, política 12–128, rehash y ADMIN normalizado; duplicados rechazados. |
| JWT y /me | Expiración, firma inválida, manipulación, sub inválido/inexistente, secreto obligatorio y respuestas sin hash. |
| RBAC | Roles permitidos, 403, inactivo 401 y cambios de rol sin otro token; un claim role no sobreescribe DB. |
| Auditoría | Bootstrap y login exitoso/fallido/inactivo auditados; RBAC denegado auditado; sin password/hash/token en details ni logs. |
| Inmutabilidad | INSERT permitido; UPDATE y DELETE de filas rechazados por PostgreSQL con SQLSTATE 55000. |
| Migraciones | head → 0001 → head y head → base → head correctos en la BD descartable. Tabla, función y trigger se eliminan/recrean. |
| Metadata | alembic check sin diferencias tanto en desarrollo como en la imagen Docker nueva. |
| Ruff | check y format --check aprobados. |
| Frontend | lint, format:check y build aprobados; sin cambios en frontend. |
| Configuración | uv sync --frozen y lock check correctos; Compose válido y backend nuevo healthy. |
| CI | actionlint válido; se conserva PostgreSQL efímero y ambos jobs anteriores, sin nuevos secrets. |

También se ejecutó el CLI real en una terminal virtual, con contraseña aleatoria
oculta y confirmación. La salida no contenía password ni hash. En esa misma BD
descartable, un proceso Uvicorn real pasó login y /me por HTTP, errores genéricos,
cambio de rol y desactivación conservando el token. Se verificaron cinco eventos
persistentes sin credenciales en details ni logs. Después se detuvo el proceso y
se revirtió la BD descartable. No se crearon ADMIN ni eventos de prueba en desarrollo.

En desarrollo solo se hizo upgrade de 0001 a 0003. La comparación de n8n antes y
después mantuvo **160 tablas, 1270 columnas y 1429 constraints** idénticos. La API,
el proxy del frontend y n8n responden salud 200. OpenAPI publica exactamente
/health, /api/auth/login y /api/auth/me; /me sin token responde 401.

Para evitar diferencias falsas de claves foráneas en Alembic se usa metadata
con esquema por defecto y search_path=public, conservando public explícito en
las revisiones. No se modificó 0001_create_users ni se tocaron objetos de n8n.

El secreto JWT local se generó aleatoriamente dentro de `.env` ignorado con permisos
600, sin imprimirlo. Los tests generan sus propias claves; CI no requiere secrets
adicionales. El CI remoto de Fase 2B sobre
`84a9592caf2ecf2b7e577e8fea46f23b7f72c2f7` terminó en **SUCCESS**,
según la ejecución posterior al push confirmada por el usuario.

Se mantienen las limitaciones documentadas en [autenticación](authentication.md):
sin refresh/revocación por sesión, recuperación, MFA, CRUD, frontend de auth ni
rate limiting/lockout. El trigger protege UPDATE/DELETE, no acciones DDL de un
propietario. Las pruebas siguen siendo secuenciales y sobre una BD descartable.

## Fase 3: contexto organizacional

Se partió de `main` limpio en `84a9592`. Se añadieron únicamente ExecutiveContact,
Vendor y sus APIs backend, usando la autenticación, RBAC y auditoría existentes.

| Comprobación | Resultado |
| --- | --- |
| Suite completa con PostgreSQL 18 | **130 pruebas aprobadas**, sin omisiones: 44 unitarias y 86 de integración; 71 casos nuevos respecto a las 59 de Fase 2B. |
| Contexto | Crear, consultar, listar, PATCH parcial, normalización, validación, paginación y desactivar/reactivar correctos; sin DELETE. |
| Identidades | Duplicados por casing rechazados mediante API y SQL directo; conflictos de POST/PATCH devuelven 409 sin detalles SQL. |
| Lookups | Coincidencia canónica exacta; inactivos excluidos por defecto. |
| RBAC | ADMIN/MANAGER escriben; los cuatro roles leen. ANALYST/AUDITOR reciben 403 al escribir; sin token/inactivo 401. Cambiar rol en DB afecta al mismo token. |
| Auditoría | Ocho acciones de contexto, actor/rol/recurso correctos; details solo contiene nombres de campos modificados. Sin valores bancarios, emails, passwords o tokens. |
| Atomicidad | Un fallo real de FK al insertar AuditLog revierte CREATE y PATCH de ambos recursos; no se convierte en 409. |
| Append-only | Los tests existentes siguen verificando INSERT permitido y UPDATE/DELETE rechazados con SQLSTATE 55000. Trigger de 0003 intacto. |
| Migración 0004 | Base limpia → head; head → 0003 → head; head → 0001 → head y head → base → head aprobados exclusivamente en PostgreSQL descartable. |
| Metadata/constraints | Tablas, índices UNIQUE funcionales, timestamps con timezone y alembic check correctos. Revisiones 0001–0003 sin modificar. |
| Backend | uv sync --frozen, Ruff check y format --check aprobados. Sin dependencias nuevas. |
| Frontend | npm ci y lint/format:check/build aprobados; ningún archivo frontend modificado. |
| CI | actionlint válido; workflow y PostgreSQL efímero sin cambios. CI remoto de Fase 3 pendiente; no se hizo push. |
| Docker | Compose config válido; imagen backend construida, upgrade y alembic check desde esa imagen correctos; cuatro servicios healthy. |

Un proceso Uvicorn real conectado a la BD descartable pasó login, creación de ambos
recursos, consulta, desactivación, normalización y 401/403. Con el mismo JWT, cambiar
el rol en PostgreSQL cambió la autorización. Los eventos conservaron la IP del peer
127.0.0.1 aunque se envió X-Forwarded-For falso. No hubo credenciales, token ni
referencia bancaria en details o logs. OpenAPI contiene 11 operaciones en 7 paths:
las 3 de salud/auth anteriores y 8 de contexto; ninguna operación DELETE.

En desarrollo se aplicó únicamente upgrade de 0003 a 0004, sin datos de prueba.
La comparación de metadata de n8n antes/después fue idéntica: **160 tablas,
1270 columnas y 1429 constraints**. No se modificaron n8n, sus workflows,
Compose, frontend ni CI. Los ciclos destructivos se limitaron a la BD de tests.

TestClient, conexiones a PostgreSQL, Uvicorn y Docker se validaron fuera del sandbox
por sus restricciones de sockets. No quedaron validaciones locales pendientes.
La validación remota de esta fase corresponderá al próximo push del usuario.

Limitaciones y decisiones menores: dominios ASCII/punycode sin DNS; un email por
ejecutivo y un dominio por proveedor; listados como arrays; PATCH sin cambios no
se audita; updated_at usa SQLAlchemy y SQL directo debe gestionarlo. Ver
[contexto organizacional](organizational-context.md). No hay motor BEC, análisis,
scoring, LLM, frontend de gestión ni workflows: **Fase 4 no fue implementada**.
