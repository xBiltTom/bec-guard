# Autenticación, RBAC y auditoría — Fase 2B

Esta fase es exclusivamente backend. Solo añade `POST /api/auth/login` y
`GET /api/auth/me`; no hay registro público, CRUD de usuarios ni frontend de login.

## Identidad y contraseñas

Toda asignación de email mediante User, el bootstrap y login utiliza trim de
espacios exteriores y lowercase. Las entradas de identidad de CLI/API se validan
con Pydantic EmailStr y email-validator, sin consultas de entregabilidad DNS.
PostgreSQL protege además la unicidad mediante `uq_users_email_lower`, un índice
UNIQUE sobre `lower(email)`, incluso frente a escrituras SQL directas con casing
distinto. Los escritores SQL externos también deben normalizar espacios.

La revisión 0002 bloquea users durante la migración, comprueba colisiones con la
misma política de normalización y solo después actualiza emails existentes. Una
colisión aborta toda la transacción sin fusionar ni eliminar usuarios. El downgrade
restaura la restricción anterior, pero no recupera el casing/espacios originales.

Las contraseñas nuevas deben tener entre **12 y 128 caracteres**, sin reglas de
composición adicionales. No se recortan ni se cambian sus caracteres. pwdlib con
su backend argon2-cffi utiliza **Argon2id**, salt automático y parámetros
recomendados por la librería. `hash_password` y `verify_password` separan claramente
ambas operaciones. `verify_and_rehash` permite actualizar parámetros al autenticar;
el nuevo hash solo se confirma tras un login válido de una cuenta activa.

Para un email inexistente se verifica un hash dummy generado una vez por proceso,
reduciendo diferencias evidentes de tiempo frente a contraseña incorrecta. No se
promete tiempo constante para toda la petición. Contraseñas de login también
tienen máximo 128; el mínimo de 12 se exige al crear contraseñas nuevas.

## Crear el primer ADMIN

Primero aplica las migraciones. Desde `backend/`:

```bash
uv sync --frozen
uv run alembic upgrade head
uv run python -m app.scripts.create_admin
```

Con Docker, en una terminal interactiva:

```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.create_admin
```

El comando solicita nombre, email, contraseña oculta y confirmación. No acepta
contraseñas por argumentos ni por pipes. Solo imprime el UUID creado. Rechaza
emails ocupados y se niega a crear otro ADMIN si ya existe uno, incluso inactivo.
Un bloqueo de tabla serializa intentos concurrentes de bootstrap. Usuario y evento
ADMIN_BOOTSTRAPPED se confirman en la misma transacción.

No se crea ninguna cuenta automáticamente ni se insertan credenciales en
migraciones. Alembic y este CLI necesitan configuración de BD, pero no un secreto
JWT. Los marcadores de password_hash usados antes en pruebas de Fase 2A no sirven
para autenticar y no se convierten automáticamente en contraseñas reales.

## Configuración JWT

| Variable | Regla |
| --- | --- |
| JWT_SECRET_KEY | Obligatoria para arrancar la API; mínimo 32 caracteres. Generar aleatoriamente y guardar solo en `.env`/entorno. |
| JWT_ACCESS_TOKEN_MINUTES | Default 30, entre 1 y 1440 minutos. |
| JWT_ALGORITHM | HS256; no se acepta un algoritmo elegido por el token. |

Puedes generar una clave con `openssl rand -hex 32`. `.env.example` la deja vacía.
AuthSettings es independiente de Settings de BD para no exigir JWT al migrar o
crear el primer ADMIN. Sus errores de configuración no muestran valores de entrada.

PyJWT emite únicamente access tokens con `sub` (UUID), `iat` y `exp`. No incluyen
role, email, nombre, hash ni secretos. Se exige la presencia de los tres claims,
firma HS256 válida, timestamps válidos y sub UUID. No hay refresh tokens, revocación
por sesión ni logout server-side. Rotar la clave invalida los tokens anteriores.

## Contratos HTTP

`POST /api/auth/login` recibe JSON:

```json
{"email":"admin@example.com","password":"<PASSWORD>"}
```

HTTP 200 devuelve únicamente:

```json
{"access_token":"<ACCESS_TOKEN>","token_type":"bearer","expires_in":1800}
```

Email inexistente, contraseña incorrecta o usuario inactivo reciben el mismo
HTTP 401, `{"detail":"Invalid credentials"}`, con `WWW-Authenticate: Bearer`.
Entrada inválida recibe 400 genérico; no se reflejan los valores de validación,
ya que podrían contener la contraseña. Un fallo de base de datos responde 503.
No hay endpoint público que pueda producir un conflicto de alta: los duplicados
se gestionan como errores limpios del CLI interno.

`GET /api/auth/me` exige `Authorization: Bearer <ACCESS_TOKEN>`. Devuelve solo
id, name, email, role, is_active y created_at. Tokens ausentes, expirados,
manipulados, con firma/sub inválidos o usuarios inexistentes/inactivos reciben 401.
Cada petición carga el User actual de PostgreSQL: un cambio de rol o desactivación
tiene efecto en la siguiente petición sin emitir otro token.

Ejemplos con placeholders, sin credenciales reales:

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  --data '{"email":"admin@example.com","password":"<PASSWORD>"}'
curl http://localhost:8000/api/auth/me \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

Para probar con una contraseña real sin escribirla en shell history, se puede
generar el JSON mediante entrada oculta y enviarlo por stdin:

```bash
python3 -c 'import getpass,json; print(json.dumps({"email":"admin@example.com","password":getpass.getpass("Password: ")}))' \
  | curl -sS http://localhost:8000/api/auth/login -H 'Content-Type: application/json' --data-binary @-
```

Usar HTTPS en un despliegue público; el Compose actual sigue siendo local.

## RBAC

`require_roles(Role.ADMIN, Role.MANAGER)` es una dependencia reutilizable que
primero usa `get_current_user`. Un token válido no basta: se consulta el User y
se exige que continúe activo. Se comprueba su rol actual, sin confiar en un claim
role aunque aparezca en un token firmado. Sin autenticación devuelve 401; con
usuario activo pero rol no permitido, 403. No existe una matriz de permisos ni
endpoints de demostración en la API real: el router protegido vive solo en tests.

## AuditLog

`public.audit_log` contiene UUID, actor_user_id nullable (FK a users), actor_role
nullable como snapshot, action, resource_type/resource_id nullable, ip_address
nullable, details JSONB nullable y created_at con timezone. El UUID se genera en
la aplicación y la fecha en PostgreSQL. La FK RESTRICT impide borrar un usuario
referenciado; no cambia registros históricos al modificar su rol.

Se registran ADMIN_BOOTSTRAPPED, LOGIN_SUCCEEDED, LOGIN_FAILED, LOGIN_INACTIVE
y RBAC_DENIED. No se registra cada `/me` exitoso. Un actor desconocido queda null.
La IP procede del peer directo, sin confiar en cabeceras de forwarding.

`record_security_event` solo admite acciones y motivos internos predefinidos.
Los details contienen, como máximo, un motivo fijo; nunca se copian email
introducido, password, password_hash, JWT, cabeceras, cuerpo HTTP ni correos.
No hay endpoints de auditoría ni métodos de aplicación para modificarla.

Un trigger BEFORE UPDATE OR DELETE rechaza cambios de filas con SQLSTATE 55000.
INSERT funciona y DROP TABLE durante downgrade también. Esto previene mutaciones
accidentales; no pretende impedir que el propietario/superusuario quite el trigger,
haga TRUNCATE o cambie DDL. Los privilegios de producción quedan por definir.

## Migraciones y pruebas

```text
0001_create_users (histórica, intacta)
  -> 0002_auth_identity_constraints
  -> 0003_create_audit_log
```

En la base descartable se prueba head → 0001 → head y también head → base → head,
incluyendo eliminación/recreación de tabla, función y trigger. `alembic check`
comprueba metadata. Las migraciones siguen siendo explícitas, solo sobre public,
sin tocar n8n. No ejecutar downgrade sobre auditoría o usuarios que quieras conservar.

Usa el PostgreSQL descartable y TEST_DATABASE_URL descritos en
[persistencia](persistence.md#pruebas-de-integración). Los tests generan sus propias
claves JWT aleatorias; CI no necesita un secreto de autenticación del repositorio.
La limpieza hace TRUNCATE únicamente en esa BD protegida de tests, sin desactivar
el trigger ni debilitarlo para las pruebas.

Quedan pendientes: frontend de auth, CRUD de usuarios, refresh, recuperación,
MFA/OAuth, rate limiting/lockout y políticas concretas de permisos de funciones
futuras. No se implementaron entidades ni funcionalidades de Fase 3.

Referencias: [FastAPI, pwdlib y JWT](https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/),
[pwdlib](https://frankie567.github.io/pwdlib/reference/pwdlib/),
[PyJWT](https://pyjwt.readthedocs.io/en/latest/usage.html).
