# Orquestación BEC Guard — n8n 2.44.4

`workflows/bec-analysis-webhook.json` recibe un EmailIngestRequest normalizado:
Webhook → configuración → ingestión idempotente FastAPI → análisis FastAPI →
Switch → respuesta ALERT / NO_ALERT / ERROR. No calcula scoring ni determina
política de alertas. No usa Code, Gmail, IMAP, SMTP ni notificaciones.

## Configurar e importar

En `.env` local ignorado, configurar AUTOMATION_API_KEY aleatoria de al menos
32 caracteres (la misma para backend y n8n). No escribirla en el workflow.
`BEC_GUARD_BACKEND_URL` tiene default `http://backend:8000`, accesible dentro de
la red Compose; nunca usar localhost para conectar esos contenedores.

```bash
docker compose up --build -d --wait backend n8n
docker compose exec backend alembic upgrade head
docker compose exec -T n8n node /opt/bec-guard-n8n/import-workflow.mjs --publish
docker compose restart n8n
docker compose up -d --wait n8n
```

Para importar sin publicar, omitir `--publish`. La importación usa el propietario/
proyecto personal que n8n asigna por defecto; no crea usuarios ni service accounts.
Los comandos CLI operan sobre la instancia local y sus datos, no sobre Git.

El JSON canónico está inactive, sin pinData ni secretos. Usa IDs lógicos estables
para que repetir el import actualice el mismo workflow/credencial. El importador
lee key y URL del entorno del contenedor, crea una credencial Generic Header Auth
`BEC Guard automation` (`X-BEC-Automation-Key`) y la importa mediante el CLI oficial.
n8n conserva el valor cifrado con la clave de su volumen. El archivo temporal de
credencial tiene permisos 0600 y se elimina al finalizar; nunca se exporta al repo.
La credencial se usa tanto en el Webhook como en los dos HTTP Request.

En esta versión instalada, `$env` está bloqueado si
N8N_BLOCK_ENV_ACCESS_IN_NODE no es exactamente `false`, confirmado en
`n8n-workflow/dist/cjs/workflow-data-proxy-env-provider.js`. No se relaja ese control.
El importador coloca la URL no secreta en el nodo Configuration; los HTTP Request
la referencian. Cambiar URL/key requiere reiniciar con el entorno actualizado y
reimportar. No se entrega el entorno a los nodos ni se usa una expresión con key.

También se puede importar el JSON desde el editor: crear/seleccionar la credencial
Header Auth anterior y reemplazar `SET_BACKEND_URL_ON_IMPORT` en Configuration por
la URL de backend. Publicar desde el editor. El CLI `publish:workflow` requiere
reiniciar n8n para registrar el webhook en el proceso que ya estaba ejecutándose.
Conservar `n8n_data`: contiene la clave de cifrado y credenciales.

## Invocar

Webhook publicado: `POST http://localhost:5678/webhook/bec-guard/analyze`.
Exige el mismo header de automatización. Ejemplo sin secretos reales:

```bash
curl -X POST http://localhost:5678/webhook/bec-guard/analyze \
  -H 'Content-Type: application/json' \
  -H 'X-BEC-Automation-Key: <LOCAL_AUTOMATION_KEY>' \
  --data '{"message_id":"<n8n-example@fixtures.becguard.example>","sender_email":"persona@organizacion.example","subject":"Revisión de expediente","body_text":"Revisar por el canal habitual.","received_at":"2026-10-21T05:00:00Z"}'
```

Sustituir el placeholder sin guardar la key real en shell history; para uso local
puede construirse la petición mediante un script que lea `.env` sin imprimirla.
El JSON debe cumplir el contrato de ingestión; no se acepta MIME ni metadata de
dataset. El endpoint del editor `/webhook-test/` solo sirve mientras está escuchando.

## Respuestas y reintentos

ALERT exige COMPLETED, HIGH/CRITICAL y alert_id; NO_ALERT exige COMPLETED,
LOW/MEDIUM y alert_id null. ERROR se evalúa primero; también es el fallback para
errores de transporte, respuestas inesperadas o inconsistentes. Nunca se enruta
un fallo a NO_ALERT. Las respuestas exitosas incluyen IDs, status, score, nivel,
tipo, summary y recommended_action. No incluyen body, sender, subject, secretos,
prompt, AuditLog ni raw provider output.

Los HTTP Request capturan status/body de respuestas no 2xx, sin retry automático.
ERROR semántico conserva error_code e IDs cuando existen. Fallos de ingestión o
infraestructura usan BACKEND_INGEST_ERROR / BACKEND_ANALYSIS_ERROR sanitizados.
El webhook responde 200 para ALERT/NO_ALERT; ERROR usa 503 para LLM_NOT_CONFIGURED
y 502 para otros errores del pipeline. No sustituye la autenticación HTTP del
Webhook: un header ausente/incorrecto recibe 401 de n8n antes de ejecutar.

Repetir el Message-ID exacto recupera el Email sin sobrescribirlo ni otra auditoría
EMAIL_INGESTED. COMPLETED se reutiliza; ERROR permite retry explícito sobre el mismo
análisis. La creación de BECAlert y su política >=70 pertenecen a FastAPI.

## Privacidad de ejecuciones

Se verificaron los nombres contra `@n8n/config/dist/configs/executions.config.js`
de 2.44.4. Compose configura:

```text
EXECUTIONS_DATA_SAVE_ON_ERROR=none
EXECUTIONS_DATA_SAVE_ON_SUCCESS=none
EXECUTIONS_DATA_SAVE_ON_PROGRESS=false
EXECUTIONS_DATA_SAVE_MANUAL_EXECUTIONS=false
EXECUTIONS_DATA_PRUNE=true
EXECUTIONS_DATA_MAX_AGE=24
```

El workflow también desactiva guardado de éxitos/errores, ejecuciones manuales y
progreso. El correo y header circulan en memoria durante la ejecución; no se
conservan como execution data terminada ni pinData. No se guarda raw MIME.
El pruning limita metadata restante a 24 horas de forma periódica, no inmediata.
Esta configuración no borra datos históricos anteriores que ya existieran.

Para depurar: respuesta HTTP sanitizada y su error_code, estado/readiness de n8n,
IDs persistidos en FastAPI y logs operativos sin payload. El editor puede mostrar
datos durante una ejecución manual activa; evitar pinning y exports con datos.
Desactivar el guardado reduce la capacidad de reproducir ejecuciones desde n8n:
el retry se hace enviando nuevamente el correo normalizado.

Referencias: [ejecuciones](https://docs.n8n.io/hosting/configuration/environment-variables/executions/),
[CLI import/publish](https://docs.n8n.io/hosting/cli-commands/).

## Alcance

Compose sigue siendo local, con puertos en loopback. El Webhook permite demostrar
orquestación sin una cuenta de correo externa. Gmail/IMAP/Graph, notificaciones,
frontend e HITL requieren fases posteriores. ALERT/NO_ALERT se prueban con fakes
backend; la validación local sin LLM usa ERROR LLM_NOT_CONFIGURED sin gastar tokens.
