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
| CI | actionlint válido; workflow y PostgreSQL efímero sin cambios. CI remoto de Fase 3 SUCCESS sobre 60bea5a; push posterior realizado por el usuario. |
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
El usuario confirmó que el CI remoto de Fase 3 sobre
`60bea5a714cc2f6908556459297b869c7d257eac` terminó en **SUCCESS**.

Limitaciones y decisiones menores: dominios ASCII/punycode sin DNS; un email por
ejecutivo y un dominio por proveedor; listados como arrays; PATCH sin cambios no
se audita; updated_at usa SQLAlchemy y SQL directo debe gestionarlo. Ver
[contexto organizacional](organizational-context.md). No hay motor BEC, análisis,
scoring, LLM, frontend de gestión ni workflows: **Fase 4 no fue implementada**.

## Fase 4: emails, MIME y dataset controlado

Se partió de `main` limpia en `60bea5a`, sincronizada con origin/main. No hubo
bloqueos de arquitectura. El contrato conceptual antiguo del analizador se alineó
con los campos planos de ingestión; su implementación sigue pendiente.

| Comprobación final | Resultado |
| --- | --- |
| Suite backend con PostgreSQL 18 real | **243 pruebas aprobadas**, sin omisiones: 140 unitarias y 103 de integración; 113 casos nuevos respecto a las 130 de Fase 3. |
| Ingestión | Persistencia completa, UUID, UTC, JSONB de destinatarios, normalización y Message-ID único exacto. Duplicado por API/SQL rechazado; distinto casing conserva identidad independiente. |
| API | POST 201, GET summary/detail 200, paginación cronológica y desempate por UUID; summary sin body_text; sin PATCH/DELETE. Errores 400/401/403/404/409/503 comprobados. |
| RBAC | ADMIN/MANAGER/ANALYST ingieren, AUDITOR solo lee. Los cuatro roles leen; cambios de rol/actividad en DB afectan al JWT existente. |
| Auditoría | EMAIL_INGESTED con actor/rol, recurso, peer directo y details null; sin direcciones, subject, body, Message-ID, MIME, hash o JWT. |
| Atomicidad | FK de actor inexistente revierte Email y AuditLog. Un trigger temporal de fallo de INSERT en auditoría devuelve 503 y deja ambas tablas sin filas del intento. El trigger append-only original permanece intacto. |
| MIME | **38 casos**: 15 fixtures .eml sintéticos más mensajes en memoria; plain/alternative/HTML, UTF-8/Latin-1, headers seleccionados, attachments ignorados y mensajes no soportados rechazados. |
| Contrato normalizado | **36 casos**: listas deduplicadas, campos opcionales, NUL/LF, longitudes, fechas aware/UTC y rechazo de metadata de evaluación. Fechas que desbordan UTC se rechazan limpiamente. |
| Límites MIME | 2 MiB raw, 200k caracteres de cuerpo, 998 de subject/Message-ID, 4096 de Authentication-Results, 100 destinatarios, profundidad 20 y 256 partes visitadas; duplicados de metadata MIME rechazados. |
| Dataset | **22 pruebas** y CLI aprobados. 140 casos, 100 LEGITIMATE/40 BEC, development 98/holdout 42, 30 hard negatives; IDs únicos, emails válidos, metadata separada y dominios reservados. |
| Tipos anotados BEC | 12 EXECUTIVE_IMPERSONATION, 10 VENDOR_FRAUD, 8 BANK_ACCOUNT_CHANGE, 6 SENSITIVE_DATA_REQUEST, 4 OTHER. Solo ground truth, sin clasificador. |
| Migraciones | Base limpia → head, head → 0004 → head y head → base → head aprobados en BD descartable. Se conservan los ciclos previos. 0001–0004 sin cambios. |
| Metadata | alembic check sin diferencias en PostgreSQL descartable y desde la imagen backend contra desarrollo. |
| Backend | uv sync --frozen, Ruff check y format --check aprobados. Sin nuevas dependencias ni cambios de lockfile. |
| Frontend | npm ci, lint, format:check y build aprobados. El intento offline requirió descargar una dependencia ausente; validación completada. Sin cambios frontend. |
| Docker | Compose config válido, imagen reconstruida y backend actualizado healthy. Migración explícita 0004 → 0005 aplicada sin datos de prueba en desarrollo. |
| CI | Workflow y servicios sin cambios: PostgreSQL efímero solo backend, sin n8n. CI remoto posterior de Fase 4 SUCCESS en f777f283b50ca4126d5b6a1573d5366a377590ab, confirmado por el usuario al iniciar Fase 5. |

También se probó un proceso Uvicorn real sobre PostgreSQL descartable: MIME → DTO →
POST, duplicado 409, resumen/detalle, errores sanitizados, permisos con el mismo
JWT y desactivación. AuditLog conservó el peer 127.0.0.1 frente a X-Forwarded-For
falso; los logs no contenían subject, body, direcciones, Message-ID, password/hash
ni token. OpenAPI ofrece **14 operaciones en 9 paths**, tres nuevas para emails.
La BD descartable se revirtió a base después de esta comprobación.

Los servicios de desarrollo estaban detenidos al comprobar infraestructura. Se
iniciaron con sus volúmenes existentes, se reconstruyó backend y quedaron los
cuatro healthy. API y proxy de frontend devuelven el contrato de salud; readiness
de n8n responde 200. Antes/después de 0005, n8n mantuvo idénticas **160 tablas,
1270 columnas y 1429 constraints**. No se tocaron sus tablas ni workflows.
No se crearon emails ni eventos EMAIL_INGESTED de prueba en desarrollo.

Las pruebas no usan SQLite ni servicios externos; EmailStr no consulta DNS.
TestClient/HTTP local, PostgreSQL y Docker se ejecutaron fuera del sandbox por sus
restricciones de sockets. No quedan verificaciones locales pendientes; la ejecución
remota de esta fase corresponde al posterior push del usuario.

Decisiones y límites: el parser usa stdlib, reemplaza bytes inválidos de charsets
conocidos y rechaza charsets desconocidos; HTML se convierte sin ejecución/red.
No se conservan raw MIME, attachments o todos los headers. Sin Message-ID o fecha
aware, MIME queda fuera del MVP. El corpus es sintético y holdout no se utilizará
para calibrar reglas. CLI de dataset desde el checkout del host; corpus no incluido
en la imagen API. Ver [ingestión](email-ingestion.md) y [dataset](dataset.md).
Al cerrar Fase 4 todavía no se había implementado Fase 5: sin reglas, similitud, scoring, clasificación,
EmailAnalysis, BECAlert, LangChain/LLM, conectores, workflows ni frontend de emails.

## Fase 5: motor BEC completo

Inicio: `main` limpia en `f777f283b50ca4126d5b6a1573d5366a377590ab`, con CI remoto
de Fase 4 **SUCCESS**, según confirmación del usuario. Se completaron checkpoints
5A, 5B, 5C y 5D con commits locales separados, sin push. No se implementó Fase 6.

5A pasó 29 pruebas de reglas/contexto y Ruff. 5B pasó 54 pruebas unitarias de
reglas/semántica. 5C pasó la suite completa de 346 pruebas con PostgreSQL real.
5D amplía integración, privacidad de salida, nombres de proveedores y regresión.

| Comprobación final | Resultado |
| --- | --- |
| Backend con PostgreSQL 18 real | 358 pruebas: 228 unitarias y 130 de integración; 115 nuevas frente a las 243 de Fase 4. |
| Reglas y contexto | Ejecutivo legítimo/suplantado, vendor legítimo/lookalike/contacto externo, nombre de proveedor de una palabra, Reply-To, Return-Path, auth fail, pagos, urgencia aislada, bank change, datos y hard negatives. |
| Semántica sin red | Factory real de los tres adaptadores y schema nativo sin invocación externa; fakes para salida válida/inválida, timeout, provider error, ausencia/config inválida y prompt injection. |
| Privacidad | No se registran keys/body/prompt/raw output; referencias bancarias conocidas redactadas aun con casing/quotes; NUL y texto vacío semántico rechazados. LangSmith tracing desactivado durante la invocación. |
| Scoring | Pesos fijos det-v1; media 50/50 hybrid-v1 con floor 70 cuando det>=70; límites 39/40, 69/70 y 84/85 comprobados. |
| API/persistencia | POST/GET, RBAC actual por DB, 400/401/403/404, COMPLETED idempotente, ERROR con riesgo null, HTTP 502/503 y retry conservando UUID. |
| Concurrencia e integridad | Dos solicitudes del mismo Email producen una fila y una llamada; FK/UNIQUE/CHECKs comprobados con PostgreSQL. |
| Auditoría | EMAIL_ANALYZED/EMAIL_ANALYSIS_FAILED sin datos del correo; fallo de auditoría revierte creación/error/retry y conserva el resultado anterior. Trigger append-only histórico intacto. |
| Migraciones | head → 0005 → head y head → base → head correctos en BD descartable; ciclos históricos conservados. Alembic check sin diferencias. 0001–0005 intactas. |
| Ruff/lock | uv sync --frozen, Ruff check y format --check aprobados. Python 3.14 y dependencias existentes conservados. |
| Dataset | Validación estructural heredada de los 140 casos aprobada. Sin cambios al corpus/contexto. |
| Regresión development | Solo 98 casos: legítimos 70, scores 0–26 (media 3.83); BEC 28, scores 15–90 (media 62.64). Los 21 hard negatives legítimos LOW. Sin llamadas LLM reales. |
| Holdout | No se evaluó ni se usó contenido/labels para tuning. Solo las validaciones estructurales heredadas. Test sentinel impide acceder a email/labels holdout desde el harness. |
| Frontend | npm ci, lint, format:check y build aprobados; sin modificaciones del frontend. |
| CI | actionlint 1.7.12 aprobado. Workflow sin cambios; PostgreSQL efímero, sin API keys, proveedores, n8n ni servicios nuevos durante tests. |
| Docker/Compose | Config válido, imagen backend reconstruida con dependencias fijadas, backend actualizado healthy y upgrade 0005→0006 aplicado en desarrollo. Alembic check desde la imagen sin diferencias. |
| Salud/OpenAPI | API y proxy frontend /health 200, n8n readiness 200. OpenAPI: 16 operaciones en 11 paths, incluidas las dos rutas de análisis. |
| n8n intacto | Metadata anterior/posterior idéntica: 160 tablas, 1270 columnas y 1429 constraints. Sin workflows ni cambios a su esquema/volúmenes. |

El harness `python -m app.scripts.check_development` no escribe DB ni imprime
cuerpos. La opción explícita `--llm` permite semántica; no se ejecutó contra
proveedores reales durante esta fase. Las pruebas cubren también su camino
híbrido con fake y que los errores nunca entran como LOW al resumen.

Se conserva un aviso de deprecación en google-genai sobre `_UnionGenericAlias`
con Python 3.14; no se oculta globalmente ni afecta a las pruebas. Las pruebas
con fakes verifican integración/contrato, no calidad real o inmunidad del LLM.
Reglas y corpus sintético no permiten afirmar precisión en producción.
Los detalles funcionales y límites se documentan en [motor BEC](bec-analysis.md).

Los ciclos destructivos se limitaron a PostgreSQL 18 descartable. En desarrollo
solo se aplicó upgrade; email_analysis quedó con cero filas, sin datos sintéticos
ni auditoría de pruebas. Las migraciones históricas, frontend, dataset, workflow CI
y n8n/workflows conservan diff vacío respecto a Fase 4. La ejecución remota de
Fase 5 se ejecutó después del push del usuario: CI #6 terminó en **SUCCESS** sobre
`feff2b018dbca5499caab326535f2e6e8e5db166`, confirmado al iniciar Fase 6.
No se hizo push durante el trabajo de Fase 5.

## Fase 6: alertas automáticas y orquestación operativa

Inicio: main limpia en `feff2b018dbca5499caab326535f2e6e8e5db166`, con los cuatro
commits de Fase 5 revisados y CI #6 SUCCESS confirmado por el usuario. Se trabajó
en checkpoints 6A/6B/6C/6D con commits locales separados, sin squash ni push.

| Comprobación | Resultado |
| --- | --- |
| Backend completo, PostgreSQL 18 real | **403 aprobadas**: 231 unitarias y 172 de integración. **45 nuevas** respecto a las 358 de Fase 5. |
| BECAlert | HIGH/CRITICAL, 70 exacto, 69, LOW/MEDIUM y ERROR; OPEN/verdict null, idempotencia, recuperación de COMPLETED antiguo sin gasto LLM, FK/UNIQUE/CHECK y lectura sin body. |
| Atomicidad | Fallo real de auditoría revierte nuevo análisis/alerta, alerta de análisis antiguo y pipeline automatizado. Los eventos exitosos no quedan parcialmente persistidos. |
| Automatización | Key correcta/incorrecta/ausente/no configurada, compare_digest, SecretStr, scopes sin bypass JWT, 201 nuevo/200 duplicado, sin sobrescritura ni evento extra; humano conserva 409. |
| Pipeline y concurrencia | HIGH con alert_id, LOW/MEDIUM sin alerta, ERROR con riesgo null, retry mismo analysis UUID y una alerta. Carreras de ingestión y análisis sin duplicados, una llamada semántica en COMPLETED concurrente. |
| Auditoría | Humanos conservan User/rol; automatización actor/rol null. EMAIL_INGESTED, EMAIL_ANALYZED, EMAIL_ANALYSIS_FAILED y BEC_ALERT_CREATED con metadata mínima, details null y sin contenido del correo. |
| HTTP real | Uvicorn sobre BD descartable: automatización HIGH/LOW/ERROR/retry, humano HIGH, GET alerts/list/detail por los cuatro roles, sin cuerpos, 401 y PATCH/DELETE 405. No se inyectó fake provider en producción. |
| Migraciones | head → 0006 → head, head → base → head y ciclos históricos aprobados en BD descartable; Alembic check sin diferencias. 0001–0006 intactas. |
| Ruff/dependencias | uv sync --frozen, check y format --check aprobados; sin nuevas dependencias ni cambio de lockfiles. |
| Dataset | Validador estructural heredado aprobado; dataset/contexto intactos. Holdout no evaluado ni usado para tuning/decisiones de esta fase. |
| Development smoke | 98 casos, resultados idénticos a Fase 5: 70 legítimos 0–26, 28 BEC 15–90, 21 hard negatives legítimos LOW; ningún ajuste de scoring. |
| Frontend | npm ci, lint, format:check y build aprobados; sin cambios frontend. |
| CI | actionlint 1.7.12 aprobado; workflow y PostgreSQL efímero conservados, sin n8n ni proveedores en CI. Equivalente local aprobado; sin ejecución remota de Fase 6 durante este trabajo. |
| Docker/Compose | Config válido, imagen backend reconstruida, upgrade 0006→0007 aplicado solo hacia adelante en desarrollo; backend, frontend, PostgreSQL y n8n healthy. |
| n8n 2.44.4 | Workflow importado y publicado con CLI oficial; readiness 200. JSON canónico inactive, sin pinData/secrets; Webhook, Set, HTTP Request, IF, Switch y Respond. Tres tests de artefacto aprobados. |
| Webhook real | Correo sintético → ingestión autenticada → EmailAnalysis ERROR LLM_NOT_CONFIGURED → HTTP 503/route ERROR, riesgo null y ninguna alerta. Sin llamadas OpenAI/Gemini/Groq. |
| Routing del artefacto | Expresiones reales del JSON ejecutadas con entradas sintéticas dentro del contenedor: HIGH/CRITICAL→ALERT, LOW/MEDIUM→NO_ALERT, ERROR e inconsistencias→ERROR. Sin llamadas a backend/LLM en esa comprobación. |
| Privacidad n8n | Save success/error/manual/progress desactivados. Se verificó soft-delete inicial y borrado físico periódico: cero filas conservan el body del smoke. Hard-delete cada minuto, buffer 0; metadata restante con max age 24h. |
| Secretos | Key local aleatoria generada en .env ignorado con permisos 600, sin mostrarla. Credencial n8n cifrada, key ausente de archivos versionables y key/body ausentes de logs operativos comprobados. `$env` sigue bloqueado en nodos. |
| Estructura n8n | Metadata anterior/posterior idéntica: **160 tablas, 1270 columnas y 1429 constraints**. Solo datos de credencial/workflow/ejecución gestionados mediante mecanismos propios de n8n. |

La lectura de código instalado confirmó el bloqueo de `$env` y los nombres de
variables de ejecución. El importador toma entorno desde el proceso administrativo,
crea una credencial Header Auth y fija la URL en Configuration; no relaja controles
globales. Los archivos temporales con credencial se crean 0600 y se eliminan.

Con save=none n8n conserva inicialmente datos de recuperación y marca deletedAt
al terminar; esa fila puede conservar status running hasta su borrado físico.
No se confundió ese registro con una ejecución activa. Se ajustó el hard-delete a
un minuto sin buffer y se verificó la limpieza real, sin modificar tablas n8n.
No es borrado instantáneo ni una garantía de deadline ante fallo del servicio.

Quedó en desarrollo un correo sintético con Message-ID
`<phase6-webhook-smoke@fixtures.becguard.example>`, su análisis ERROR y auditoría
actor null, como evidencia del camino real. El resto de fixtures/usuarios y el
servidor HTTP de validación se limitaron a PostgreSQL descartable y se limpiaron.
No se añadieron usuarios ficticios a desarrollo ni se gastaron tokens LLM.

Se mantiene el aviso de deprecación upstream de google-genai ya documentado.
No se implementó frontend, HITL, asignación, veredicto, cierre, Gmail/IMAP/Graph ni
notificaciones. Alcance y límites: [alertas y orquestación](alerts-and-orchestration.md)
y [guía operativa n8n](../n8n/README.md).
