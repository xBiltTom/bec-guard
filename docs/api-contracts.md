# Contratos de API y análisis

## Autenticación implementada (Fase 2B)

`POST /api/auth/login` recibe JSON email/password y devuelve un access token.
`GET /api/auth/me` requiere Bearer y devuelve únicamente la identidad segura.
Contratos, códigos de error y ejemplos: [autenticación](authentication.md#contratos-http).

## Contexto organizacional implementado (Fase 3)

GET/POST de `/api/executives` y `/api/vendors`, GET/PATCH por UUID, paginación,
RBAC y respuestas: [contratos de contexto](organizational-context.md#contratos-http).
No hay DELETE ni endpoints de análisis BEC.

## Ingestión implementada (Fase 4)

`POST /api/emails` recibe EmailIngestRequest normalizado; GET colección devuelve
EmailSummaryResponse sin body_text y GET por UUID EmailDetailResponse. Sin PATCH
ni DELETE. El parser MIME es interno, no otro endpoint. Contrato, campos, límites,
RBAC y códigos: [ingestión](email-ingestion.md). Se rechaza toda metadata de dataset.

## Implementado: GET /health

No requiere autenticación. Verifica FastAPI y conectividad real a PostgreSQL
con `SELECT 1`; no crea ni modifica datos.

HTTP 200:

```json
{"status": "ok", "service": "bec-guard-api"}
```

Si la conexión falla, responde HTTP 503, sin detalles de conexión ni credenciales:

```json
{"detail": "Database unavailable"}
```

El frontend muestra “Backend conectado ✓” solo tras validar una respuesta 200
con el contrato esperado. Un timeout, error de red, HTTP no exitoso o respuesta
incompatible se muestra como no disponible. Se puede reintentar manualmente.

## Futuro: Email → BEC Analyzer → BECAnalysisResult

**Este contrato es documentación; no hay endpoint de análisis, esquema ejecutable
de IA ni llamadas a proveedores.** Es un contrato interno de aplicación y no el
formato nativo de ninguna API LLM. La ingestión ya existe como POST /api/emails;
el endpoint de análisis es futuro.

### Entrada: Email normalizado

El analizador futuro consumirá la representación normalizada persistida en Fase 4,
con UUID interno y Message-ID. La entrada de POST no recibe el UUID ni ingested_at.
Ejemplo del subconjunto relevante para el futuro analizador:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "message_id": "<sample@correo.example>",
  "sender_name": "Dirección Ficticia",
  "sender_email": "direccion@organizacion.example",
  "reply_to": null,
  "to_recipients": ["finanzas@organizacion.example"],
  "cc_recipients": [],
  "subject": "Solicitud de transferencia urgente",
  "body_text": "Necesito que revises esta transferencia con urgencia.",
  "received_at": "2026-10-20T15:00:00Z"
}
```

El contrato completo de ingestión incluye Return-Path y Authentication-Results
seleccionados, con emails/fechas/límites validados. El parser MIME transforma el
mensaje al mismo schema; no se guarda raw MIME ni attachments. No se confía en
nombres visibles ni en el contenido como instrucciones del sistema. La metadata
del dataset nunca forma parte de esta entrada.

El analizador obtendrá el contexto organizacional desde servicios del backend.
El frontend y n8n no tendrán que construir prompts ni suministrar credenciales LLM.

### Salida: BECAnalysisResult

```json
{
  "risk_score": 82,
  "risk_level": "HIGH",
  "bec_type": "EXECUTIVE_IMPERSONATION",
  "signals": [
    {
      "code": "AUTHORITY_PRESSURE",
      "description": "El mensaje invoca autoridad y solicita una acción urgente.",
      "source": "SEMANTIC"
    }
  ],
  "summary": "Solicitud que requiere verificar la identidad del remitente.",
  "recommended_action": "Confirmar la solicitud por un canal independiente."
}
```

El ejemplo es ilustrativo y no representa un cálculo implementado.

| Campo | Contrato previsto |
| --- | --- |
| risk_score | Entero de 0 a 100 inclusive; no es una probabilidad calibrada. |
| risk_level | Uno de LOW, MEDIUM, HIGH, CRITICAL. La relación con el score dependerá de la política versionada del motor. |
| bec_type | Uno de los valores BECType del dominio, o `null` si no hay patrón identificado. |
| signals | Lista de señales; puede estar vacía. Cada señal contiene `code` estable, `description` legible y `source` (RULE, CONTEXT o SEMANTIC). |
| summary | Texto no vacío, útil para revisión humana. |
| recommended_action | Texto no vacío que recomienda una acción; no la ejecuta. |

Todos los campos de salida son obligatorios, incluido `bec_type` aunque sea `null`.
Un correo sin señales BEC puede producir `signals: []`, `bec_type: null` y un nivel
LOW. Los umbrales, catálogo de señales y política de alertas se definirán en la
fase del motor. No se debe utilizar el ejemplo como implementación de scoring.

### Independencia de proveedor y errores

El caso de uso futuro dependerá de una interfaz propia de análisis. Un adaptador
podrá usar LangChain y OpenAI, Gemini, Groq u otro proveedor. El backend combinará
reglas, contexto y análisis semántico para producir este resultado validado.
Respuestas nativas, tokens y objetos de SDK no cruzarán este límite del dominio.

Un timeout, fallo de proveedor o respuesta inválida será un error de análisis;
**no se transformará en un resultado LOW**. El formato HTTP de dichos errores,
reintentos y procesamiento asíncrono se definirá al implementar el caso de uso.
Proveedor, modelo, versión de política y fechas se conservarán como metadatos de
EmailAnalysis para auditoría sin alterar este contrato de resultado.

Las claves de API solo existirán en configuración del backend. Las variables
`LLM_PROVIDER`, `LLM_MODEL`, `OPENAI_API_KEY`, `GOOGLE_API_KEY` y `GROQ_API_KEY`
están reservadas en `.env.example`, vacías y sin efecto en las fases actuales.
