# Contratos de API y análisis

## Autenticación, contexto e ingestión

`POST /api/auth/login` recibe email/password y devuelve access token.
`GET /api/auth/me` requiere Bearer y devuelve identidad segura.
Ver [autenticación](authentication.md#contratos-http).

GET/POST de `/api/executives` y `/api/vendors`, GET/PATCH por UUID, paginación y
RBAC: [contexto organizacional](organizational-context.md#contratos-http).
No hay DELETE.

`POST /api/emails` recibe EmailIngestRequest; GET colección devuelve resúmenes sin
body_text; GET por UUID devuelve detalle. Sin PATCH/DELETE ni upload MIME.
Contrato, límites y RBAC: [ingestión](email-ingestion.md). Se rechaza metadata de
dataset: label, split, expected_bec_type e is_hard_negative no son entrada del motor.

## GET /health

Sin autenticación. Comprueba API y PostgreSQL mediante SELECT 1; no escribe.

HTTP 200:

```json
{"status": "ok", "service": "bec-guard-api"}
```

Fallo de BD: HTTP 503, sin detalles de conexión:

```json
{"detail": "Database unavailable"}
```

## POST /api/emails/{email_id}/analyze

Implementado en Fase 5. Bearer obligatorio; ADMIN/MANAGER/ANALYST pueden ejecutar,
AUDITOR recibe 403. No recibe body: carga el Email persistido y contexto activo,
aplica reglas, semántica LangChain y scoring híbrido, y guarda EmailAnalysis con
auditoría atómica. Desde Fase 6, COMPLETED >=70 garantiza BECAlert OPEN/verdict null
en la misma transacción. No ejecuta recomendaciones.

HTTP 200: EmailAnalysisResponse COMPLETED, creado o reutilizado. Si ya existe
COMPLETED no llama otra vez al proveedor. Si le falta alerta y score>=70, la crea
con BEC_ALERT_CREATED; si ya existe, no repite eventos. Si existe ERROR,
recalcula y actualiza la misma fila/UUID. UNIQUE email_id y bloqueo de Email
serializan solicitudes concurrentes; no hay historial de ejecuciones.

Ejemplo ilustrativo (50% de 80 + 50% de 90 = 85):

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440001",
  "email_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "COMPLETED",
  "deterministic_score": 80,
  "semantic_score": 90,
  "risk_score": 85,
  "risk_level": "CRITICAL",
  "bec_type": "EXECUTIVE_IMPERSONATION",
  "signals": [
    {
      "code": "EXECUTIVE_IDENTITY_MISMATCH",
      "description": "Nombre ejecutivo conocido con dirección no oficial.",
      "source": "CONTEXT",
      "contribution": 35
    },
    {
      "code": "BYPASS_APPROVAL",
      "description": "La solicitud intenta omitir una aprobación independiente.",
      "source": "SEMANTIC",
      "contribution": 0
    }
  ],
  "summary": "Solicitud con indicios de suplantación que requiere verificación.",
  "recommended_action": "Confirmar por un canal independiente conocido.",
  "provider": "openai",
  "model": "<CONFIGURED_MODEL>",
  "policy_version": "det-v1/semantic-v1/hybrid-v1",
  "error_code": null,
  "analyzed_at": "2026-10-21T05:00:00Z"
}
```

Las señales del ejemplo están abreviadas; no representan todas las contribuciones
del score ilustrativo. El backend devuelve la lista completa calculada.

| Campo | Contrato |
| --- | --- |
| id / email_id | UUID del análisis actual y del Email. |
| status | COMPLETED o ERROR. |
| deterministic_score | Entero 0–100, siempre disponible. |
| semantic_score / risk_score | Enteros 0–100 en COMPLETED; null en ERROR. No son probabilidades. |
| risk_level | LOW 0–39, MEDIUM 40–69, HIGH 70–84, CRITICAL 85–100; null en ERROR. |
| bec_type | EXECUTIVE_IMPERSONATION, VENDOR_FRAUD, BANK_ACCOUNT_CHANGE, SENSITIVE_DATA_REQUEST, OTHER o null. Siempre null bajo 40 y en ERROR. |
| signals | code estable, description hasta 240, source RULE/CONTEXT/SEMANTIC, contribution 0–100. Semántica tiene contribution=0, pues participa mediante semantic_score. |
| summary / recommended_action | Hasta 600/400 caracteres, no vacíos en COMPLETED; null en ERROR. |
| provider / model | Configuración usada cuando está disponible; nullable en ERROR. Nunca claves. |
| policy_version | Versiones determinista, prompt y scoring. |
| error_code | Código fijo sanitizado en ERROR; null en COMPLETED. |
| analyzed_at | Fecha de la última ejecución, con timezone UTC. |

La clasificación final desde 40 prefiere el patrón observado por reglas/contexto
y después el sugerido por semántica; puede ser null si ninguno identifica tipo.
OTHER no significa legítimo. La ponderación, floor y precedencia exacta de tipos
locales están en [política BEC](bec-analysis.md#scoring-híbrido-hybrid-v1).

## Fallo semántico

POST devuelve HTTP 502 para timeout, fallo del proveedor o salida inválida; 503
para configuración ausente/inválida. El cuerpo es EmailAnalysisResponse con
status ERROR, error_code LLM_TIMEOUT / LLM_PROVIDER_ERROR / LLM_INVALID_OUTPUT /
LLM_NOT_CONFIGURED. Conserva deterministic_score y señales RULE/CONTEXT. Los
campos semántico/final, risk_level, bec_type, summary y recommended_action son null.

**ERROR no es LOW ni LEGITIMATE ni score cero.** El resultado ERROR y
EMAIL_ANALYSIS_FAILED quedan persistidos y pueden consultarse después. Repetir
POST permite retry; no hay retry automático ni fallback a otro proveedor.

Un fallo de persistencia/auditoría devuelve el 503 genérico `Database unavailable`
y revierte el intento. Ese error de infraestructura no tiene el contrato de un
ERROR semántico persistido. Las respuestas no incluyen raw output, prompt ni
detalles internos del proveedor.

## GET /api/emails/{email_id}/analysis

Los cuatro roles autenticados leen EmailAnalysisResponse, con HTTP 200 tanto
para COMPLETED como ERROR. HTTP 404 si no existe Email o si no tiene análisis.
No dispara LLM ni modifica/audita el resultado.

Ambas rutas: 401 para token ausente/inválido o usuario inactivo; 400 para UUID
inválido; POST 404 para Email inexistente antes de crear/configurar un modelo.
Se consulta siempre User actual en PostgreSQL para autorización.

La API puede arrancar sin claves LLM. Configuración, seguridad, prompt injection,
límites y pruebas sin red: [motor BEC](bec-analysis.md).

## GET /api/alerts y GET /api/alerts/{alert_id}

Todos los roles autenticados leen. Lista: array paginado con id, analysis_id,
email_id, status, verdict, assigned_to, risk_score, risk_level, bec_type, sender_name,
sender_email, subject, received_at, created_at y updated_at. No carga ni devuelve
body_text. Orden created_at DESC/id ASC; limit default 50 (1–100), offset default 0.

Detalle: campos de alerta, resolution/closed_at nullable y EmailAnalysisResponse
anidado en analysis, sin cuerpo del correo. 404 si no existe; UUID inválido 400;
sin token/usuario inactivo 401. Sin PATCH/DELETE ni acciones HITL.

## POST /api/automation/emails

Exige X-BEC-Automation-Key, independiente del JWT humano. Body EmailIngestRequest.
Respuesta `{created: boolean, email: EmailDetailResponse}`. Message-ID exacto nuevo:
201/true. Existente: 200/false, mismo Email sin sobrescritura ni otra auditoría.
El POST humano conserva 409. La carrera UNIQUE recupera el ganador persistido.

## POST /api/automation/emails/{email_id}/analyze

Misma autenticación. Reutiliza analyze_email y devuelve
`{analysis: EmailAnalysisResponse, alert_id: UUID|null}`. COMPLETED HIGH/CRITICAL
incluye alert_id; LOW/MEDIUM y ERROR lo dejan null. HTTP 200 COMPLETED, 502 fallo
LLM, 503 falta de configuración, 404 Email inexistente. ERROR nunca significa LOW.
Retry explícito actualiza el mismo análisis; COMPLETED reutiliza resultado/alerta.

La API key se carga lazy, SecretStr y compare_digest. Ausente/corta (<32) en
configuración: 503 Automation unavailable. Header ausente/incorrecto: 401 genérico.
No autoriza ninguna otra ruta; JWT no sustituye esta key. Auditoría del pipeline
automatizado usa actor_user_id/actor_role null, details null y recurso/acción/IP/
timestamp. La auditoría humana conserva User y rol actual.

Workflow, política alert-v1, transacciones y privacidad:
[alertas y orquestación](alerts-and-orchestration.md).
