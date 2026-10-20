# Persistencia de Fase 2A

El dominio persistente actual es únicamente `User`. No hay endpoints de usuarios,
autenticación, JWT, RBAC funcional, auditoría persistente ni otras entidades SQL.

## Modelo y decisiones

`app.models.Base` concentra la metadata en `public` y nombres estables de
constraints. `app.models.User` define `public.users`:

| Campo | Tipo y comportamiento |
| --- | --- |
| id | UUID, clave primaria, UUID v4 generado con `uuid4` al insertar mediante SQLAlchemy. |
| name | VARCHAR(200), obligatorio. |
| email | VARCHAR(320), obligatorio y UNIQUE (`uq_users_email`). |
| password_hash | TEXT obligatorio; sin default ni lógica de hashing. |
| role | VARCHAR(7) obligatorio, con CHECK `ck_users_role`. Sin default: el creador deberá elegir un rol. |
| is_active | BOOLEAN obligatorio, default de servidor `true`. |
| created_at | TIMESTAMP WITH TIME ZONE obligatorio, default de servidor `CURRENT_TIMESTAMP`. |
| updated_at | Igual que created_at al insertar; SQLAlchemy emite `CURRENT_TIMESTAMP` al actualizar. |

El UUID se genera en la aplicación para no depender de extensiones ni funciones
PostgreSQL. No existe default SQL para `id`: las escrituras SQL directas deben
proporcionarlo. El índice creado por UNIQUE ya cubre email; no se añade otro índice
redundante. La comparación de emails es sensible a mayúsculas y no se normaliza
todavía. Antes de implementar altas en Fase 2B se deberá definir y aplicar una
política de normalización consistente.

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

`password_hash` almacenará únicamente hashes. Fase 2A no acepta contraseñas, no
crea usuarios reales ni implementa funciones para producir o verificar hashes.
Los tests usan un marcador opaco exclusivo de pruebas, no una contraseña ni un
hash utilizable. Hashing y autenticación pertenecen a Fase 2B.

## Sesiones

El lifespan de FastAPI crea un engine y una fábrica `sessionmaker` por aplicación.
`get_session` en `app/core/database.py` abre y cierra una Session por petición para
futuras rutas. Quien realiza una escritura debe hacer `commit` explícito;
cerrar una sesión revierte lo no confirmado. Se usa `expire_on_commit=False`.
`/health` conserva su dependencia Connection y su contrato original.

## Alembic

`alembic.ini` no contiene URL ni credenciales. `migrations/env.py` utiliza
`Settings().database_url` y el mismo constructor de engine del backend. Las
variables del sistema prevalecen sobre `.env` de la raíz. Se usa el objeto URL
directamente, evitando problemas con contraseñas que contienen `%` u otros
caracteres especiales. No se imprimen credenciales ni parámetros SQL.

La revisión inicial `0001_create_users` crea solo `public.users` y sus constraints.
Alembic administra además `public.alembic_version`. No crea un tipo enum SQL
independiente. `downgrade` elimina exclusivamente `public.users`; Alembic conserva
su tabla de versiones vacía al llegar a base.

La metadata y las operaciones de la revisión indican `public` explícitamente.
La autogeneración excluye n8n y cualquier tabla fuera de la metadata. Por ello,
eliminar un modelo no genera automáticamente un DROP para esa tabla: habrá que
escribir y revisar la operación de migración. Tampoco se debe confiar en que
autogenerate detecte cambios en los valores del CHECK de Role; deben revisarse
expresamente. Nunca edites revisiones ya aplicadas: añade una nueva.

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

Revertir esta revisión elimina users y sus datos. No ejecutes este ciclo en
desarrollo si necesitas conservar usuarios. No modifiques `n8n` para hacer una
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
n8n. Las pruebas de salud siguen siendo unitarias.

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

Las fixtures aplican la migración, permiten commits reales y limpian las filas de
users después de cada test. Al terminar revierten a base. El test de migraciones
confirma users + alembic_version, downgrade con desaparición de users, nuevo
upgrade y ausencia de diferencias con la metadata. Los otros tests comprueban
lectura desde otra sesión, los cuatro roles, UUID, defaults, timestamps, email
duplicado e imposibilidad de escribir roles inválidos directamente en SQL.
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
