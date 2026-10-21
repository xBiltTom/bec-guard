# Alertas, revisión humana y orquestación

FastAPI conserva reglas, contexto, LangChain, scoring y política de alertas. n8n
solo orquesta correo normalizado → ingestión → análisis → respuesta. No hay broker,
workers nuevos, proveedor de correo ni notificaciones. Fase 7 añade frontend e HITL.

## BECAlert y alert-v1

La revisión nueva `0007_bec_alerts`, dependiente de `0006_email_analysis`, crea
`public.bec_alerts`. No modifica 0001–0006 ni el esquema n8n. Campos: id UUID,
analysis_id FK RESTRICT y UNIQUE, status, verdict nullable, assigned_to nullable
FK RESTRICT a users, resolution nullable, created_at/updated_at UTC y closed_at
nullable. CHECKs permiten OPEN/UNDER_REVIEW/CLOSED, verdict null/CONFIRMED_BEC/
FALSE_POSITIVE y exigen closed_at null en OPEN. No existe PENDING.

Una alerta nueva tiene OPEN, verdict/assigned_to/resolution/closed_at null.
Fase 7 añade claim/release/resolve humanos y 0008 exige coherencia por estado.
No hay DELETE ni reopen.
El índice created_at DESC + id sirve al listado real; no se añade índice por status
sin un filtro que lo consuma. PK y UNIQUE analysis_id cubren identidad e idempotencia.

`ALERT_POLICY_VERSION = "alert-v1"`: únicamente COMPLETED con risk_score >=70
genera alerta. HIGH/CRITICAL sí, LOW/MEDIUM no, ERROR no aunque deterministic_score
sea 100. Las políticas det-v1, semantic-v1 y hybrid-v1 permanecen sin cambios.

`ensure_alert_for_analysis` participa en la transacción del caller y serializa por
EmailAnalysis. Reutiliza la alerta existente o crea una y BEC_ALERT_CREATED, sin
commit independiente. analyze_email mantiene su bloqueo por Email y llama al
helper también cuando encuentra un COMPLETED antiguo: recupera alertas faltantes
de Fase 5 sin volver a llamar al LLM. No hay backfill en Alembic.

Para un nuevo HIGH/CRITICAL, EmailAnalysis + BECAlert + EMAIL_ANALYZED +
BEC_ALERT_CREATED comparten commit. Si falla inserción/auditoría, se revierte el
intento. En recuperación de un COMPLETED antiguo se conserva ese análisis y se
revierte solo el intento de alerta. UNIQUE analysis_id protege además PostgreSQL.
Repetir un resultado completado con alerta no repite eventos ni gasto semántico.

## Lectura de alertas

GET /api/alerts y GET /api/alerts/{alert_id} exigen JWT humano. Los cuatro roles
activos leen; sin token/inactivo 401, UUID inválido 400, alerta inexistente 404.
No existen PATCH/DELETE; Fase 7 usa POST claim/release/resolve.

Lista: array con id, analysis_id, email_id, status, verdict, assigned_to, risk_score,
risk_level, bec_type, sender_name, sender_email, subject, received_at, created_at y
updated_at. Selecciona columnas explícitas sin cargar body_text. Orden created_at
DESC, id ASC; limit 50 por defecto (1–100), offset 0 (>=0), con filtros status/risk_level/bec_type/assigned_to/analysis_id.

Detalle: datos de alerta, resolution, closed_at y EmailAnalysisResponse anidado en
analysis. No incluye cuerpo del correo; Email detail sigue disponible por separado.

## Autenticación de automatización

AUTOMATION_API_KEY es SecretStr, opcional al arrancar y sin secreto predeterminado.
Se carga de forma lazy al usar automatización. Una key ausente o de menos de 32
caracteres produce 503 Automation unavailable. Se recomienda generar 48 bytes
aleatorios con secrets.token_urlsafe y conservarlos solo en `.env` ignorado/entorno.
`.env.example` contiene el campo vacío; Compose lo pasa solo a backend y n8n.

Header X-BEC-Automation-Key: comparación de bytes UTF-8 mediante
secrets.compare_digest. Header ausente/incorrecto recibe el mismo 401 genérico.
Nunca se devuelve ni registra el valor. La key no sustituye JWT ni da permisos
para auth, alert reads, emails genéricos, contexto o administración. JWT tampoco
sustituye esa key en las dos rutas de automatización. No se crea SYSTEM, usuario
ficticio, service principal, OAuth ni tabla de credenciales del backend.

## Contratos de automatización

POST /api/automation/emails recibe exactamente EmailIngestRequest. Devuelve:

```json
{"created": true, "email": "<EmailDetailResponse object>"}
```

Nuevo: 201, created=true, Email y EMAIL_INGESTED en un commit. Message-ID exacto
existente: 200, created=false, mismo Email, sin sobrescribirlo ni otro evento.
Se reutiliza ingest_email: el wrapper primero consulta y recupera el ganador tras
una carrera UNIQUE. Solo ese conflicto se traduce a duplicado; otros fallos de BD
siguen siendo 503. POST /api/emails humano conserva 409 en duplicados.

POST /api/automation/emails/{email_id}/analyze reutiliza analyze_email. Devuelve:

```json
{"analysis": "<EmailAnalysisResponse object>", "alert_id": null}
```

200 COMPLETED; HIGH/CRITICAL tienen UUID alert_id, LOW/MEDIUM null. ERROR deja
alert_id y riesgo null; 502 para timeout/provider/output, 503 para configuración
LLM ausente/inválida. Email inexistente 404. Los objetos de los ejemplos son
schemas anidados reales, no strings. Fallos de persistencia/auditoría usan el 503
genérico Database unavailable; no afirman que el resultado se guardó.

ERROR admite retry explícito, conservando analysis.id y creando como máximo una
alerta cuando el retry resulta HIGH/CRITICAL. COMPLETED reutiliza resultado/alerta.
No hay bucle automático de retries en n8n.

## Auditoría

Los endpoints humanos siguen exigiendo User. Solo los helpers de ingestión,
análisis y alerta aceptan actor opcional. Automatización autenticada por key pasa
actor_user_id=null y actor_role=null. Para estas acciones de pipeline, actor null
identifica automatización; no implica una identidad humana anónima autorizada.
Las acciones históricas de login con actor null conservan su significado anterior.

HIGH nuevo genera EMAIL_INGESTED, EMAIL_ANALYZED, BEC_ALERT_CREATED: con User/rol
para humano y ambos null para automatización. ERROR genera EMAIL_ANALYSIS_FAILED,
sin alerta. Cada evento contiene acción, resource_type/resource_id, peer IP y fecha;
details=null. No guarda scores, señales, remitente, subject, body ni output LLM.
El trigger append-only se mantiene. Se prueban rollback humano, automatizado y de
recuperación de COMPLETED antiguo ante fallo real de auditoría.

## Workflow operativo

[Guía n8n](../n8n/README.md): configuración, importación, publicación y sample curl.
El JSON versionado usa Webhook, Set, HTTP Request, IF, Switch y Respond to Webhook.
Está inactive, con IDs lógicos estables, sin pinData ni secretos. La instancia local
lo publica mediante el CLI oficial. El Webhook exige Header Auth usando la misma
credencial cifrada que las dos llamadas HTTP a FastAPI.

La instalación 2.44.4 bloquea `$env` por defecto. Se conserva ese control: el
importador lee BEC_GUARD_BACKEND_URL/AUTOMATION_API_KEY desde el entorno, fija la
URL en Configuration y crea una credencial Header Auth. No se habilita acceso al
entorno desde nodos. El JSON guarda referencias a credencial, nunca su valor.

ERROR se evalúa primero; ALERT exige COMPLETED + HIGH/CRITICAL + alert_id;
NO_ALERT exige COMPLETED + LOW/MEDIUM + alert_id null. Una respuesta inesperada,
fallo de transporte o resultado inconsistente va a ERROR. No contiene lógica BEC,
regex, comparación de dominios, thresholds de scoring ni política de creación.

## Privacidad y validación

Se desactiva guardado n8n de éxito, error, manual y progreso tanto en Compose como
en el workflow. n8n crea un registro inicial temporal y lo marca deletedAt al
terminar cuando save=none. El hard-delete cada minuto, sin buffer, borra su payload;
una ejecución activa todavía puede tener datos transitorios. No se guarda MIME ni
pinData. La metadata restante se poda periódicamente a 24 horas. Detalles y nombres
de variables verificados contra código instalado, no solo documentación genérica.

El smoke local usa un correo sintético con Message-ID estable y LLM sin configurar:
Webhook → ingestión autenticada → EmailAnalysis ERROR LLM_NOT_CONFIGURED → HTTP 503,
route ERROR, riesgo null y ninguna alerta. Se comprueba la auditoría actor null,
credencial cifrada, logs sin key/body y limpieza de execution data. No se usa ninguna
key real de OpenAI/Gemini/Groq ni se añade un proveedor fake a producción.

Backend demuestra ALERT/NO_ALERT/ERROR/retry/concurrencia con fakes inyectados.
Uvicorn real sobre PostgreSQL descartable valida GET alerts para los cuatro roles,
lista/detalle sin cuerpo, 401 y ausencia de PATCH/DELETE. El esquema n8n conserva
160 tablas, 1270 columnas y 1429 constraints; solo cambian sus datos de workflow/
credencial/ejecución a través de mecanismos propios de n8n.

Holdout y dataset intactos: sin evaluación, inspección manual ni tuning. La
regresión development solo se ejecuta como smoke del motor existente. Límites:
proceso síncrono, key única sin scopes dinámicos, red local, eliminación periódica
(no instantánea) de datos temporales. No hay proveedor de correo real ni notificaciones. Frontend y revisión humana están en Fase 7.


## HITL humano (Fase 7)

La automatización conserva scope exclusivo ingest/analyze; jamás claim/release/resolve.
0008 exige OPEN con assigned_to/verdict/resolution/closed_at null, UNDER_REVIEW con
assigned_to presente y resto null, CLOSED con los cuatro presentes. No hay cambios
de catálogo ni backfill. Claim y decisiones se serializan por fila de BECAlert.
ADMIN/MANAGER/ANALYST escriben con JWT; ANALYST solo libera/resuelve su asignación,
supervisores cualquiera. Resolución trim obligatoria 1–2000, fecha de cierre UTC.
Idempotencia no repite eventos; CLOSED no puede cambiar de decisión ni reabrirse.
Los eventos humanos CLAIMED/RELEASED/CONFIRMED/FALSE_POSITIVE no incluyen resolución,
score ni contenido; actor es User obligatorio y mutación/auditoría son atómicas.
[Contratos](api-contracts.md) · [aplicación React](frontend.md).
