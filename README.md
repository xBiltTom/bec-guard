# BEC Guard

Proyecto académico de Ingeniería de Software para la detección y gestión de
Business Email Compromise (BEC) / fraude ejecutivo. Su objetivo futuro es combinar
reglas deterministas, contexto de ejecutivos y proveedores, análisis semántico,
evaluación de riesgo, revisión humana y auditoría.

**Estado actual: Fases 0, 1, 2A, 2B y 3.** Hay persistencia de User, AuditLog,
ExecutiveContact y Vendor, autenticación backend con Argon2id y JWT, APIs de
contexto organizacional protegidas por RBAC y auditoría atómica, y una pantalla mínima
que comprueba la salud de FastAPI y PostgreSQL. No hay frontend de autenticación.
Todavía no se analizan correos ni se generan alertas.

La minifase de consolidación separa conceptualmente el estado operativo de la
alerta (`status`) de su veredicto humano (`verdict`, inicialmente `null`) y confirma
exactamente un rol por usuario en el MVP. Fase 4 sigue pendiente.

## Arquitectura y stack

React + TypeScript + Vite consume FastAPI mediante REST. FastAPI concentra la lógica
del negocio y accede a PostgreSQL mediante SQLAlchemy y psycopg. Pydantic valida
la configuración y respuestas. Alembic versiona el esquema del dominio. n8n será
un orquestador de flujos, sin trasladar allí las reglas del dominio.

Versiones base: Python 3.14, Node.js 24 LTS, React 19, Vite 8, TypeScript 6,
PostgreSQL 18 y n8n 2.44.4. Las dependencias de aplicación quedan fijadas en
`backend/uv.lock` y `frontend/package-lock.json`. Se mantiene TypeScript 6 por
compatibilidad con el parser de ESLint. Los tags de Python, Node y PostgreSQL
reciben parches dentro de su versión mayor; n8n está fijado a una versión concreta.

LangChain y adaptadores multiproveedor (OpenAI, Gemini, Groq u otros) se incorporarán
en fases posteriores. No hay llamadas LLM, modelos locales, SDKs de proveedores,
Redis ni workers adicionales. Se usa CSS sencillo sin bibliotecas de componentes.

Documentación:

- [Arquitectura y flujo futuro](docs/architecture.md)
- [Dominio, entidades, roles y enums](docs/domain.md)
- [Contratos de salud y análisis futuro](docs/api-contracts.md)
- [Persistencia, migraciones y base de pruebas](docs/persistence.md)
- [Autenticación, bootstrap ADMIN, JWT, RBAC y auditoría](docs/authentication.md)
- [Contexto organizacional, endpoints, permisos y lookups](docs/organizational-context.md)
- [Validaciones ejecutadas y particularidades del entorno](docs/validation.md)

## Requisitos

- Linux y Docker Engine con daemon activo y acceso autorizado.
- Plugin Docker Compose v2 o superior: `docker compose version`.
- Conexión a Internet para descargar imágenes y dependencias la primera vez.
- Puertos 5173, 8000, 5432 y 5678 disponibles (se pueden cambiar en `.env`).

Si ya tienes PostgreSQL en el equipo usando 5432, configura `POSTGRES_PORT=5433`
en `.env`. El puerto interno de Compose permanece en 5432.

Para ejecutar todo con Docker no necesitas Python, Node, uv ni PostgreSQL instalados
en el host. Para desarrollo sin contenedores de aplicación: Python 3.14, uv 0.13.4
y Node.js 24 LTS con npm; PostgreSQL y n8n pueden permanecer en Compose.

## Configuración inicial

Desde la raíz del repositorio:

```bash
cp .env.example .env
chmod 600 .env
```

Edita `.env` y asigna una contraseña local aleatoria y no vacía a
`POSTGRES_PASSWORD` y una clave JWT independiente a `JWT_SECRET_KEY` (mínimo 32
caracteres aleatorios). Puedes generar cada valor con `openssl rand -hex 32`.
No existen credenciales predeterminadas. Las claves futuras de IA siguen vacías.

| Variable | Uso |
| --- | --- |
| POSTGRES_DB / POSTGRES_USER | Nombre de la base de datos y usuario local. |
| POSTGRES_PASSWORD | Secreto obligatorio; solo en `.env`. |
| POSTGRES_HOST | `localhost` para backend en el host; Compose usa `postgres`. |
| POSTGRES_PORT | Puerto PostgreSQL publicado en el host; internamente usa 5432. |
| BACKEND_PORT / FRONTEND_PORT / N8N_PORT | Puertos publicados, por defecto 8000 / 5173 / 5678. |
| GENERIC_TIMEZONE | Zona horaria de n8n; por defecto America/Lima. |
| JWT_SECRET_KEY | Obligatoria para la API, sin valor predeterminado; solo en `.env`/entorno. |
| JWT_ACCESS_TOKEN_MINUTES / JWT_ALGORITHM | Expiración de acceso (30 minutos por defecto) y HS256. |
| LLM_PROVIDER / LLM_MODEL | Reservadas, sin uso actual. |
| OPENAI_API_KEY / GOOGLE_API_KEY / GROQ_API_KEY | Reservadas, sin uso actual; nunca se envían al frontend. |

No ejecutes `source .env`: Compose y Pydantic leen el archivo directamente.
Para contraseñas con caracteres especiales, utiliza comillas simples en `.env`.
La URL de SQLAlchemy se construye con `URL.create`, sin concatenar credenciales.
No compartas la salida completa de `docker compose config`, ya que expande secretos;
para validar usa `--quiet`.

## Iniciar todo

```bash
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
docker compose exec backend alembic upgrade head
docker compose ps
```

La primera ejecución descarga imágenes, instala dependencias y deja que n8n cree
sus tablas internas. En ejecuciones posteriores basta `docker compose up -d`.
Las migraciones de BEC Guard son explícitas: ejecuta `alembic upgrade head` después
de actualizar el código. FastAPI no las aplica al arrancar y `/health` solo verifica
conectividad, no que el esquema esté actualizado.

| Servicio | URL o conexión local |
| --- | --- |
| React | http://localhost:5173 |
| FastAPI | http://localhost:8000 |
| Salud API y PostgreSQL | http://localhost:8000/health |
| OpenAPI / Swagger | http://localhost:8000/docs |
| n8n | http://localhost:5678 |
| PostgreSQL | localhost:5432; base y usuario definidos en `.env` |

Si cambias un puerto en `.env`, ajusta su URL. La raíz `/` de FastAPI no tiene
endpoint; utiliza `/health` o `/docs`. En n8n el primer acceso pide configurar su
cuenta propietaria. No es un login de BEC Guard.

Todos los puertos se publican solo en la interfaz de loopback. n8n permite cookies
en HTTP para esta ejecución local. Esta configuración no es un despliegue público.

## Comprobar comunicación

```bash
curl --fail http://localhost:8000/health
curl --fail http://localhost:5173/health
curl --fail http://localhost:5678/healthz/readiness
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT 1;"'
```

Las dos primeras peticiones deben responder:

```json
{"status":"ok","service":"bec-guard-api"}
```

Abre React: debe aparecer **Backend conectado ✓**. La consulta comprueba también
PostgreSQL; ante error se muestra **Backend no disponible**, con un botón para
reintentar. El navegador solicita `/health` al mismo origen y Vite reenvía la
petición a FastAPI (`http://backend:8000` dentro de Compose). No necesita CORS.

El frontend usa el servidor de desarrollo Vite dentro de Docker, sin bind mounts.
Después de editar código, reconstruye con `docker compose up --build -d` o usa
el modo de desarrollo en el host indicado más abajo.

## Pruebas y calidad

Backend, desde `backend/`:

```bash
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

La suite verifica salud, passwords, JWT, bootstrap, login/me, RBAC, persistencia,
migraciones, contexto organizacional y auditoría append-only. Las pruebas de
integración usan PostgreSQL real y requieren `TEST_DATABASE_URL`, una variable independiente de
`.env`, apuntando a una base de pruebas vacía. Sin ella se omiten las de integración.
Consulta [cómo levantar esa base y ejecutar la suite completa](docs/persistence.md#pruebas-de-integración).

Frontend, desde `frontend/`:

```bash
npm ci
npm run lint
npm run format:check
npm run build
```

El build verifica TypeScript y genera `dist/`. No se añade un framework de pruebas
del frontend en esta fase. Usa `npm run format` y `uv run ruff format .` para aplicar
el formato de cada aplicación.

### Integración continua

El workflow [CI](.github/workflows/ci.yml) se ejecuta en pushes a `main` y pull
requests hacia `main`. Usa dos jobs independientes en Ubuntu: backend con Python
3.14 y uv 0.13.4, y frontend con Node.js 24. Instala desde los lockfiles y ejecuta
las mismas pruebas, linting, comprobaciones de formato y build descritos arriba.
Reutiliza las cachés de uv y npm. El job backend incluye un PostgreSQL 18 efímero
de pruebas y configura `TEST_DATABASE_URL`; pytest aplica las migraciones y prueba
upgrade/downgrade/upgrade. No requiere secretos, `.env`, n8n ni Docker Compose.
El job frontend no usa PostgreSQL. No realiza despliegues.

## Primer ADMIN y autenticación

Después de aplicar las migraciones, abre una terminal interactiva:

```bash
docker compose exec backend python -m app.scripts.create_admin
```

Solicita nombre, email y contraseña oculta con confirmación; no acepta passwords
como argumentos ni crea usuarios automáticamente. En el host, desde `backend/`:
`uv run python -m app.scripts.create_admin`. El bootstrap rechaza emails ocupados
y otro ADMIN existente.

La API ofrece `POST /api/auth/login` (JSON email/password) y `GET /api/auth/me`
(Bearer). El token de acceso dura 30 minutos por defecto; rol y estado activo se
consultan en PostgreSQL en cada petición. No hay refresh tokens ni registro público.
Consulta los [contratos y ejemplos curl](docs/authentication.md#contratos-http).

## Migraciones

Desde `backend/`, usando la configuración de `.env` de la raíz:

```bash
uv run alembic upgrade head
uv run alembic current
uv run alembic check
```

Para crear una revisión: `uv run alembic revision --autogenerate -m "describe change"`.
Revisa el archivo generado antes de aplicarlo. Para revertir la última revisión:
`uv run alembic downgrade -1`. Revertir 0004 elimina ejecutivos/proveedores;
revertir 0003 elimina la auditoría; llegar a base elimina también users. El ciclo
destructivo se valida solo en la base de test.
No se modifica el esquema `n8n`. Más detalles en [persistencia](docs/persistence.md).

## Desarrollo de aplicaciones en el host

Primero configura `.env` y levanta la infraestructura:

```bash
docker compose up -d postgres n8n
```

Si backend o frontend están levantados en Compose, detenlos para liberar sus
puertos: `docker compose stop backend frontend`.

En una terminal, desde `backend/`:

```bash
uv sync --frozen
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

En otra terminal, desde `frontend/`:

```bash
npm ci
npm run dev -- --host 127.0.0.1
```

El backend carga `.env` de la raíz y el frontend utiliza `BACKEND_PORT` para su
proxy. Si cambias puertos, ajusta también los argumentos `--port` de estos comandos.
Las variables del sistema prevalecen sobre `.env`.

## Persistencia, detención y diagnóstico

```bash
docker compose stop
docker compose start
docker compose down
```

`down` elimina contenedores y red, pero conserva los volúmenes `postgres_data` y
`n8n_data`. No añadas `-v` si necesitas conservar los datos. Cambiar credenciales
en `.env` no cambia usuarios ya existentes dentro de un volumen PostgreSQL.

`docker/postgres/init.sql` solo se ejecuta al inicializar un volumen vacío y crea
el esquema `n8n`. BEC Guard usa users, audit_log y alembic_version en public después
de aplicar las migraciones.
Ambos servicios comparten usuario únicamente para este entorno local. n8n gestiona
sus propias tablas, migraciones y claves de cifrado; conserva ambos volúmenes.

Para revisar un fallo de arranque:

```bash
docker compose ps
docker compose logs --tail=80 backend
docker compose logs --tail=80 postgres
docker compose logs --tail=80 n8n
docker compose logs --tail=80 frontend
```

## Estructura

```text
backend/
  app/
    api/           # Salud, auth y contexto organizacional
    core/          # Settings y SQLAlchemy
    models/        # Base, User, Role, AuditLog, ExecutiveContact y Vendor
    schemas/       # Contratos HTTP separados
    services/      # Auth, auditoría, contexto y lookups; sin motor BEC
    scripts/       # CLI create_admin
    main.py
  tests/
  migrations/      # Alembic: env.py, plantilla y versions/
  alembic.ini
  Dockerfile
  pyproject.toml
  uv.lock
frontend/
  src/             # Pantalla mínima y consulta /health
  Dockerfile
  package.json
  package-lock.json
n8n/workflows/      # Futuras exportaciones; hoy solo README
docker/postgres/   # Inicialización del esquema de n8n
docs/              # Arquitectura, dominio y contratos
docker-compose.yml
.env.example
.gitignore
README.md
```

## Pendiente para Fase 4 y posteriores

Fase 3 añade gestión backend de ejecutivos/proveedores, lookups exactos y auditoría
atómica. Quedan pendientes frontend de autenticación y gestión, CRUD de usuarios,
recuperación, refresh tokens, ingestión de correos y parser MIME, reglas BEC, scoring,
LangChain, adaptadores LLM y prompts, revisión de alertas y workflows de n8n.
También quedan fuera dashboards, reportes, Gmail, IMAP y Microsoft Graph.

Las APIs de contexto ofrecen GET/POST/PATCH; todos los roles leen y solo ADMIN/
MANAGER escriben. No existe DELETE. Las entidades de correo/análisis/alertas y
los contratos de análisis siguen siendo diseño conceptual.
No se han agregado endpoints de negocio ficticios ni integraciones IA.
