# Contexto organizacional — Fase 3

FastAPI administra ejecutivos y proveedores conocidos en `public`. Este contexto
se reutilizará en análisis posteriores; hoy no detecta fraude ni calcula riesgo.
No hay vistas React, ingestión de correos ni workflows de n8n.

## Modelos y normalización

Ambos modelos tienen `id` UUID v4 generado por SQLAlchemy, `is_active` obligatorio
con default SQL `true` y timestamps `created_at`/`updated_at` con timezone. Conservan
la estrategia de User: PostgreSQL genera fechas, conexiones UTC y `onupdate` de
SQLAlchemy actualiza `updated_at`. SQL directo debe gestionar su propia actualización
de fecha; no hay trigger de timestamps.

| Modelo | Datos |
| --- | --- |
| ExecutiveContact / executive_contacts | name y position obligatorios, hasta 200 caracteres; department opcional hasta 200; email obligatorio hasta 320. |
| Vendor / vendors | name obligatorio hasta 200; domain obligatorio hasta 253; contact_email opcional hasta 320; bank_account_reference opcional hasta 256. |

Los textos de entrada se recortan. Los obligatorios no aceptan vacío; los opcionales
vacíos se convierten en `null`. Los emails se validan con Pydantic EmailStr y se
normalizan con trim + lowercase, igual que las identidades de autenticación.
Cada ejecutivo tiene **un email**; su dominio puede extraerse posteriormente.

El dominio principal del proveedor se recorta, pasa a lowercase y pierde un punto
final: `" Example.COM. "` → `example.com`. Se aceptan hostnames ASCII de dos o más
etiquetas (1–63 caracteres por etiqueta, letras, números y guion interior), incluidos
subdominios y representaciones punycode. IDN en Unicode debe proporcionarse como
punycode; no se intenta convertirlo. Se rechazan IPs, esquemas, rutas, queries,
fragmentos, puertos, espacios internos y etiquetas vacías. No hay consulta DNS,
validación de propiedad ni comparación de similitud.

PostgreSQL impide duplicados por casing con los índices únicos
`uq_executive_contacts_email_lower` y `uq_vendors_domain_lower` sobre `lower(email)`
y `lower(domain)`. No hay un segundo índice redundante ni CITEXT. Esta unicidad
incluye registros inactivos; desactivarlos no libera su identidad.

`contact_email` se normaliza pero no es único ni tiene que pertenecer a `domain`:
puede ser un contacto externo. `bank_account_reference` es una referencia opaca
conocida, sin reglas de banco/país. Solo se recorta y limita su longitud. No admite
el uso de PIN, CVV, claves ni credenciales bancarias. Es visible en la respuesta a
roles con permiso de lectura, pero nunca se copia a auditoría, logs o errores.

## Contratos HTTP

Todas estas rutas requieren Bearer y consultan el usuario/rol activo en PostgreSQL.

| Ruta | Métodos | Resultado |
| --- | --- | --- |
| /api/executives | GET, POST | Array paginado (200), creación (201). |
| /api/executives/{id} | GET, PATCH | Recurso (200), actualización parcial (200). |
| /api/vendors | GET, POST | Array paginado (200), creación (201). |
| /api/vendors/{id} | GET, PATCH | Recurso (200), actualización parcial (200). |

GET de colección admite `limit` (default 50, 1–100), `offset` (default 0, mínimo 0)
y `include_inactive` (default false). Devuelve un array, sin total ni envoltorio;
ordena por created_at y UUID para paginación determinista. GET por id puede devolver
un registro inactivo para consultar su contexto histórico.

POST recibe los datos del modelo, excepto id y timestamps. `is_active` puede
omitirse. PATCH solo acepta campos editables presentes: no permite `{}`, campos
desconocidos ni `null` en obligatorios; los opcionales pueden limpiarse con `null`.
Un PATCH normalizado sin cambios efectivos devuelve 200 sin generar evento.
Las respuestas usan schemas separados, incluyen los datos del recurso, UUID,
is_active y timestamps ISO 8601 con zona horaria. Nunca incluyen datos de User.

Ejecutivo, ejemplo de POST:

```json
{"name":"Ana Pérez","position":"Gerente general","department":"Dirección","email":"ana@example.com"}
```

Proveedor, ejemplo de POST:

```json
{"name":"Proveedor de ejemplo","domain":"supplier.example.com","contact_email":"contact@supplier.example.com"}
```

Para desactivar o reactivar: PATCH con `{"is_active":false}` o
`{"is_active":true}`. **No existe DELETE**; se conserva la fila.

| Código | Significado |
| --- | --- |
| 400 | Entrada inválida; respuesta sanitizada `Invalid request`, sin reflejar valores. |
| 401 | Token ausente/inválido o usuario inexistente/inactivo. |
| 403 | Usuario autenticado sin permiso de escritura. |
| 404 | Recurso inexistente. |
| 409 | Email de ejecutivo o dominio de proveedor ya registrado. |
| 503 | Fallo de persistencia, sin detalles SQL. |

Solo se traduce a 409 SQLSTATE 23505 del índice de identidad correspondiente;
otros errores no se presentan como conflictos de identidad.

## RBAC

| Rol | GET | POST / PATCH / activar / desactivar |
| --- | --- | --- |
| ADMIN | Sí | Sí |
| MANAGER | Sí | Sí |
| ANALYST | Sí | No (403) |
| AUDITOR | Sí | No (403) |

Se reutiliza `require_roles`, sin otra infraestructura de permisos. Un cambio del
rol o actividad en DB afecta a la siguiente petición usando el mismo token.

## Lookups internos

En `app.services.organizational_context`:

- `find_executive_by_email(session, email, include_inactive=False)`.
- `find_vendor_by_domain(session, domain, include_inactive=False)`.

Normalizan/validan la entrada y devuelven un modelo o `None`. Por defecto excluyen
inactivos; no hacen commit. Solo buscan coincidencia exacta canónica. No contienen
reglas BEC, heurísticas, similitud ni scoring.

## Auditoría y transacciones

Acciones: `EXECUTIVE_CREATED`, `EXECUTIVE_UPDATED`, `EXECUTIVE_DEACTIVATED`,
`EXECUTIVE_REACTIVATED`, `VENDOR_CREATED`, `VENDOR_UPDATED`, `VENDOR_DEACTIVATED`
y `VENDOR_REACTIVATED`.

Cada evento guarda actor, snapshot de rol, tipo `executive`/`vendor`, UUID del
recurso, fecha e IP del peer directo. No se confía en X-Forwarded-For. En UPDATE,
`details` solo puede contener `changed_fields` con nombres separados por comas;
nunca valores, emails, referencia bancaria, cuerpos HTTP o credenciales. En CREATE
es `null`. Si un PATCH también cambia actividad, se emite la acción de activación/
desactivación con los nombres de todos los campos cambiados, sin eventos duplicados.
No se auditan lecturas correctas; la denegación RBAC conserva su evento existente.

El servicio hace flush del recurso, añade el evento y ejecuta **un commit**. Si
falla cualquiera de las escrituras, revierte ambas. Las pruebas fuerzan un error
real de FK en la inserción del AuditLog y comprueban el rollback de CREATE/PATCH.
El trigger append-only de 0003 sigue bloqueando UPDATE/DELETE de auditoría.

## Migración y pruebas

La nueva revisión `0004_organizational_context`, archivo
`0004_create_organizational_context.py`, depende de `0003_create_audit_log` y solo
crea executive_contacts/vendors y sus índices en public. 0001–0003 siguen intactas.

```bash
# Desde backend/, con .env de desarrollo configurado:
uv run alembic upgrade head
uv run alembic check
uv run alembic current
```

Después de reconstruir la imagen: `docker compose exec backend alembic upgrade head`.
Las migraciones son explícitas; no se ejecutan dentro del proceso web.
Downgrade a 0003 elimina ambas tablas y sus datos: úsalo solo en una BD descartable.
La suite prueba head → 0003 → head, head → base → head, metadata y constraints.
Para ejecutarla con PostgreSQL real sigue [persistencia](persistence.md#pruebas-de-integración)
y configura TEST_DATABASE_URL. CI conserva el servicio PostgreSQL efímero actual.

Quedan fuera de esta fase: frontend de gestión, CRUD de usuarios, múltiples emails/
dominios por entidad, validación bancaria específica, ingestión, análisis BEC,
scoring, LLM, alertas y workflows de n8n. **Fase 4 no está implementada.**
