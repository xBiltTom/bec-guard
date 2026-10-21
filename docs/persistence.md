# Persistencia de BEC Guard

El dominio persistente actual contiene `User`, `AuditLog`, `ExecutiveContact`,
`Vendor` y `Email`. Hay autenticación backend y RBAC, sin CRUD de usuarios.
Los contratos de auth
y el bootstrap se describen en [autenticación](authentication.md). Modelos, índices
y transacciones de Fase 3 en [contexto organizacional](organizational-context.md).
Email, JSONB de destinatarios e idempotencia de Fase 4 en [ingestión](email-ingestion.md).

## Modelo y decisiones

`app.models.Base` concentra la metadata y nombres estables de constraints.
Las conexiones fijan `search_path=public`; la metadata usa el esquema por defecto
sin prefijo para que la reflexión de claves foráneas coincida con PostgreSQL.
Las revisiones sí indican public explícitamente. `app.models.User` define users:

| Campo | Tipo y comportamiento |
| --- | --- |
| id | UUID, clave primaria, UUID v4 generado con `uuid4` al insertar mediante SQLAlchemy. |
| name | VARCHAR(200), obligatorio. |
| email | VARCHAR(320), obligatorio, normalizado; índice UNIQUE `uq_users_email_lower` sobre lower(email). |
| password_hash | TEXT obligatorio, generado con Argon2id por el servicio; sin default SQL. |
| role | VARCHAR(7) obligatorio, con CHECK `ck_users_role`. Sin default: el creador deberá elegir un rol. |
| is_active | BOOLEAN obligatorio, default de servidor `true`. |
| created_at | TIMESTAMP WITH TIME ZONE obligatorio, default de servidor `CURRENT_TIMESTAMP`. |
| updated_at | Igual que created_at al insertar; SQLAlchemy emite `CURRENT_TIMESTAMP` al actualizar. |

El UUID se genera en la aplicación para no depender de extensiones ni funciones
PostgreSQL. No existe default SQL para `id`: las escrituras SQL directas deben
proporcionarlo. No se añade un segundo índice de email redundante. Fase 2B reemplaza
la unicidad exacta de 0001 por un índice funcional case-insensitive y normaliza con
trim + lowercase. La revisión 0002 aborta sin fusionar si detecta colisiones.

`app.models.enums.Role` es un `StrEnum` reutilizable: ADMIN, ANALYST, MANAGER y
AUDITOR. SQLAlchemy valida los valores y el CHECK protege también escrituras
directas. Se elige texto con constraint en lugar de un tipo enum nativo para
simplificar cambios y reversiones de valores mediante migraciones ordinarias.
Cada usuario tiene exactamente un rol, sin `user_roles` ni relación many-to-many.

PostgreSQL genera los timestamps con zona horaria y las conexiones del backend
usan UTC. `CURRENT_TIMESTAMP` representa el inicio de la transacción.
`created_at` no se modifica en actualizaciones normales. `updated_at` se gestiona
mediante `onupdate` de SQLAlchemy, **no mediante un trigger**: una actualización
SQL externa deberá asignarlo explícitamente. No se generan fechas naive en Python.
Si futuras entradas aceptan fechas, deberán validar que incluyan zona horaria.

`password_hash` almacena hashes Argon2id; el CLI de bootstrap nunca persiste la
contraseña original. Los tests de almacenamiento de User conservan un marcador
opaco no utilizable para login, mientras que los de autenticación usan hashes
reales de contraseñas exclusivas de tests. No existe creación automática de cuentas.

`AuditLog` añade trazabilidad append-only: UUID, actor nullable y snapshot de rol,
acción, recurso nullable, IP nullable, details JSONB nullable y created_at con
timezone. La FK de actor usa RESTRICT, para no modificar auditoría al borrar usuarios.
Un trigger rechaza UPDATE y DELETE; no hay rutas de modificación. Ver los eventos,
la política de datos mínimos y los límites en [auditoría](authentication.md#auditlog).

## Sesiones

El lifespan de FastAPI crea un engine y una fábrica `sessionmaker` por aplicación.
`get_session` en `app/core/database.py` abre y cierra una Session por petición para
las rutas de autenticación y futuras rutas. Quien escribe hace `commit` explícito;
cerrar una sesión revierte lo no confirmado. Se usa `expire_on_commit=False`.
`/health` conserva su dependencia Connection y su contrato original.

## Alembic

`alembic.ini` no contiene URL ni credenciales. `migrations/env.py` utiliza
`Settings().database_url` y el mismo constructor de engine del backend. Las
variables del sistema prevalecen sobre `.env` de la raíz. Se usa el objeto URL
directamente, evitando problemas con contraseñas que contienen `%` u otros
caracteres especiales. No se imprimen credenciales ni parámetros SQL.

La revisión histórica `0001_create_users` permanece intacta. 0002 normaliza
identidades y reemplaza la unicidad de email. 0003 crea audit_log y su función/trigger
append-only. 0004 añade executive_contacts y vendors con unicidad case-insensitive.
0005 crea emails con UNIQUE exacto de Message-ID e índice de orden cronológico.
0006 crea email_analysis con FK a emails, UNIQUE email_id y CHECKs de resultado;
no añade índices aparte de PK/UNIQUE. Ver [análisis BEC](bec-analysis.md).
Alembic administra además `public.alembic_version`. No hay tipos enum
SQL independientes. Al llegar a base se eliminan todas las tablas del dominio, y la tabla
de versiones queda vacía. Al bajar solo a 0001 se conservan users pero se pierde
la auditoría y la unicidad vuelve a ser exacta. No se recupera el casing original.

Las conexiones y las operaciones de migración se limitan a `public`.
La autogeneración excluye n8n y cualquier tabla fuera de la metadata. Por ello,
eliminar un modelo no genera automáticamente un DROP para esa tabla: habrá que
escribir y revisar la operación de migración. Tampoco se debe confiar en que
autogenerate detecte cambios en los valores del CHECK de Role; deben revisarse
expresamente. Lo mismo aplica a función/trigger de auditoría, gestionados manualmente
en 0003 y probados contra PostgreSQL. Nunca edites revisiones ya aplicadas.

Desde `backend/`, con PostgreSQL iniciado y `.env` configurado:

```bash
uv sync --frozen
uv run alembic upgrade head
uv run alembic current
uv run alembic history
uv run alembic check
uv run alembic revision --autogenerate -m "describe change"
```

Revisa siempre upgrade y downgrade del archivo generado antes de aplicarlo.
`alembic check` ayuda a detectar diferencias, pero no sustituye esa revisión.
Para revertir en una base descartable:

```bash
uv run alembic downgrade -1
# Solo para validar desde cero en una base de pruebas:
uv run alembic downgrade base
uv run alembic upgrade head
```

Revertir a base elimina usuarios y auditoría. No ejecutes este ciclo en
desarrollo si necesitas conservarlos. No modifiques `n8n` para hacer una
prueba ni borres volúmenes de Compose.

En Docker, la imagen incluye Alembic y las migraciones:

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
```

También puedes usar `docker compose run --rm --no-deps backend alembic upgrade head`
si PostgreSQL ya está disponible. El proceso web nunca aplica migraciones al iniciar.

## Pruebas de integración

Se usan PostgreSQL real y Alembic, sin SQLite, mocks de persistencia, create_all ni
n8n. Las pruebas de salud, passwords y JWT puros son unitarias.

Ejemplo de servidor descartable local, independiente de Compose y sus volúmenes:

```bash
docker run --rm -d --name bec-guard-test-postgres \
  --tmpfs /var/lib/postgresql \
  -e POSTGRES_DB=bec_guard_test \
  -e POSTGRES_USER=bec_guard_test \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -p 127.0.0.1:55432:5432 postgres:18-alpine
docker exec bec-guard-test-postgres pg_isready -U bec_guard_test -d bec_guard_test
```

Espera a que `pg_isready` indique que acepta conexiones. `trust` es exclusivo de
esta instancia efímera de pruebas en loopback; no se usa en el PostgreSQL de
desarrollo. No se requieren credenciales reales ni nuevas claves de CI.

Desde `backend/`:

```bash
export TEST_DATABASE_URL='postgresql+psycopg://bec_guard_test@127.0.0.1:55432/bec_guard_test'
uv sync --frozen
uv run pytest -v
# Solo integración, incluido el ciclo de migraciones:
uv run pytest -m integration -v
# Solo pruebas unitarias, sin servidor:
uv run pytest -m 'not integration'
```

La variable se lee directamente del entorno, no del `.env` de desarrollo.
Sin `TEST_DATABASE_URL`, las pruebas de integración se muestran como omitidas.
CI siempre la configura para ejecutar la suite completa.

Como protección, el nombre de la base debe ser `bec_guard_test` o empezar por
`bec_guard_test_`. La suite rechaza una base con esquema n8n, tablas preexistentes
en public o una revisión aplicada. Se permite solo `alembic_version` vacía para
repetir la suite. Un nombre de test no sustituye estas comprobaciones.

Las fixtures aplican las migraciones, permiten commits reales y limpian con
TRUNCATE audit_log + users + executive_contacts + vendors + emails únicamente en esta BD
descartable, sin quitar el trigger.
Al terminar revierten a base. Los tests verifican head → 0004 → head, head → 0003 → head,
head → 0001 → head, el ciclo hasta base, metadata match y fallo seguro ante colisiones. También comprueban User,
bootstrap, login/me, JWT, cambios de rol/actividad, RBAC, eventos y triggers;
además CRUD/lookups de contexto, emails, unicidad y atomicidad de ingestión.
Parser MIME y dataset tienen pruebas unitarias sin red ni PostgreSQL.
Ejecuta la suite secuencialmente; no está diseñada para compartir la misma base
entre ejecuciones concurrentes.

Al terminar con el servidor descartable:

```bash
docker stop bec-guard-test-postgres
unset TEST_DATABASE_URL
```

El contenedor se elimina por `--rm`. Nunca apuntes estas pruebas a desarrollo.
CI usa un service container PostgreSQL 18 solo en el job backend; no levanta
Compose ni n8n. El job frontend conserva sus comprobaciones anteriores.

Referencias: [Alembic y autogeneración](https://alembic.sqlalchemy.org/en/latest/autogenerate.html),
[defaults y onupdate de SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/defaults.html).
