# Ingestión de emails — Fase 4

BEC Guard incorpora correos normalizados como entrada persistente. **No determina
legitimidad, tipo BEC ni riesgo al ingestar.** El análisis es una operación separada
implementada en [Fase 5](bec-analysis.md); no hay alertas.

## Modelo y contrato

`app.models.Email` representa `public.emails`. UUID v4 generado por la aplicación;
Message-ID único exacto; received_at e ingested_at con timezone y conexiones UTC.
received_at procede del mensaje y es obligatorio; ingested_at lo genera PostgreSQL.
No hay updated_at porque no se ofrecen operaciones de edición de emails.

`EmailIngestRequest` es un contrato Pydantic independiente del MIME. Solo admite:

| Campo | Entrada y almacenamiento |
| --- | --- |
| message_id | Obligatorio, texto no vacío, trim exterior, conserva casing. VARCHAR(998), UNIQUE. Controles/NUL rechazados. |
| thread_id | Identificador externo opcional, trim, hasta 255; no se reconstruye ni infiere. |
| sender_name | Opcional, trim, vacío → null, hasta 200. |
| sender_email | Un único email obligatorio, validado con EmailStr, trim + lowercase, hasta 320. |
| reply_to / return_path | Email opcional con la misma validación/normalización; vacío → null. |
| to_recipients / cc_recipients | Listas JSONB, default []; emails válidos normalizados, duplicados eliminados en cada lista preservando orden. |
| subject | Default vacío, null → vacío, NUL eliminado, casing y contenido conservados. VARCHAR(998). |
| body_text | Default vacío, null → vacío; NUL eliminado y CRLF/CR convertidos a LF. TEXT. |
| authentication_results | Texto opcional, vacío → null, hasta 4096; no se interpretan SPF/DKIM/DMARC. |
| received_at | Fecha ISO 8601 con offset o datetime aware; se convierte a UTC. No acepta naive ni timestamps numéricos. |

Campos desconocidos se rechazan (`extra="forbid"`), incluidos label, expected_label,
expected_bec_type, split, bec_type, risk_score, risk_level y verdict. UUID e ingested_at
son internos y tampoco se reciben en POST. No se almacena metadata de evaluación.

Las listas vacías permiten mensajes sin To/Cc visibles. Se aceptan hasta 100
entradas por lista antes de deduplicar y un máximo combinado de 100 después de
normalizar. Un destinatario presente en To y Cc conserva ambas posiciones.

Message-ID usa igualdad exacta de PostgreSQL, con una única constraint
`uq_emails_message_id`. Repetirlo devuelve 409, sin actualizar la fila ni crear
otra auditoría. Casing diferente representa otra identidad; no hay fingerprints
alternativos. Mensajes sin Message-ID quedan fuera del MVP. El contrato JSON
admite identificadores opacos; el parser extrae el Message-ID del mensaje.

## API y permisos

| Método/ruta | Resultado |
| --- | --- |
| POST /api/emails | 201 con EmailDetailResponse. |
| GET /api/emails | 200 con array de EmailSummaryResponse. |
| GET /api/emails/{id} | 200 con EmailDetailResponse; 404 si no existe. |

Todos los roles autenticados pueden leer. **ADMIN, MANAGER y ANALYST** pueden
ingestar; AUDITOR recibe 403 en POST. Se reutiliza require_roles con rol/actividad
actuales en DB; un token emitido antes de un cambio no conserva permisos obsoletos.
Sin autenticación válida o con usuario inactivo: 401. No hay PATCH ni DELETE.

El listado acepta limit (default 50, 1–100) y offset (default 0, mínimo 0), sin
filtros de análisis. Ordena por received_at DESC y luego id ASC. El índice compuesto
`ix_emails_received_at_id` respalda ese orden. Devuelve únicamente id, message_id,
sender_name, sender_email, reply_to, subject, received_at e ingested_at: el cuerpo
no se carga desde PostgreSQL para esta consulta ni se envía en el resumen.

El detalle añade destinatarios, return_path, thread_id, body_text y
authentication_results. No devuelve User, password_hash, tokens ni labels.
Entrada inválida: 400 sanitizado; Message-ID duplicado: 409; fallos de persistencia
no identificados: 503. Solo se traduce a 409 SQLSTATE 23505 de la constraint indicada.

Ejemplo de POST (añadir el Bearer obtenido por login):

```json
{
  "message_id": "<sample-001@correo.example>",
  "sender_name": "Persona Ficticia",
  "sender_email": "persona@organizacion.example",
  "to_recipients": ["finanzas@organizacion.example"],
  "subject": "Revisión del expediente",
  "body_text": "Revisaremos el expediente en la reunión acordada.",
  "received_at": "2026-10-20T14:00:00Z"
}
```

## Parser RFC 5322 / MIME interno

`app.services.mime_parser.parse_email(raw: bytes) -> EmailIngestRequest` usa
BytesParser y policy.default de stdlib. No tiene endpoint de upload ni depende
de una cuenta de email. No hay red, ejecución de HTML, seguimiento de URLs,
almacenamiento de MIME bruto ni procesamiento de archivos adjuntos.

| Header seleccionado | Campo normalizado |
| --- | --- |
| Message-ID | message_id, conservando casing. |
| From | sender_name decodificado y exactamente un sender_email. |
| Reply-To | reply_to, como máximo uno. |
| Return-Path | return_path; el null envelope `<>` se representa como null. |
| To / Cc | Listas de direcciones sin display names. |
| Subject | subject decodificado. |
| Date | received_at UTC. |
| Authentication-Results | Texto limitado; múltiples instancias se unen con LF, sin interpretación. |

No se guardan las cabeceras completas ni las no seleccionadas. Message-ID, From
y Date son obligatorios; Date inválida o sin zona horaria se rechaza. Más de un
From/Reply-To, direcciones inválidas o headers singleton repetidos se rechazan,
sin elegir silenciosamente una alternativa. También se rechazan Content-Type,
Content-Transfer-Encoding o Content-Disposition repetidos en una parte MIME. No se infiere thread_id ni se añaden
In-Reply-To/References en este MVP.

El parser elige text/plain antes de text/html en multipart. No concatena partes.
En multipart/related respeta la raíz indicada por start o la primera parte.
Descarta partes con disposition attachment o filename y mensajes RFC822 anidados,
incluso si contienen texto plano. Un mensaje sin cuerpo textual admitido produce
body_text vacío. No se extraen contenidos de adjuntos.

Si solo hay HTML, HTMLParser extrae texto de forma determinista, convierte entidades
y añade saltos en bloques; descarta script/style/head/template y atributos. No es
un navegador, no solicita imágenes ni ejecuta scripts. No guarda HTML original.
CharSets conocidos se decodifican con replacement para bytes inválidos; un charset
no reconocido falla limpiamente. MIME malformado, estructuras excesivas y límites
excedidos producen MIMEParseError con mensaje sin contenido del correo.

## Límites centralizados

Definidos en `app/core/email_limits.py` y compartidos por contrato/parser/modelo:

| Dato | Máximo |
| --- | --- |
| Raw MIME | 2 MiB, comprobado antes de parsear. |
| body_text | 200 000 caracteres normalizados. |
| subject / message_id | 998 caracteres cada uno. |
| authentication_results | 4096 caracteres. |
| sender_name / thread_id | 200 / 255 caracteres. |
| Destinatarios | 100 combinados, con límite previo de 100 por lista. |
| Estructura MIME | Profundidad 20, hasta 256 partes visitadas para seleccionar cuerpo. |

No hay truncado silencioso. Estos límites no son un sistema de streaming ni un
almacenamiento de attachments. API JSON valida campos tras recibir el request.

## Auditoría y atomicidad

`EMAIL_INGESTED` registra actor, snapshot de rol, resource_type=email, UUID del
recurso, fecha e IP del peer directo; details es null. Nunca copia Message-ID,
direcciones, asunto, cuerpo, Authentication-Results, MIME ni JWT. No se confía en
X-Forwarded-For. No se auditan lecturas correctas ni se registra contenido en errores.

El servicio hace flush del Email, añade AuditLog y realiza un único commit. Si
falla la auditoría, ambos se revierten. Se prueba una FK inexistente y también un
trigger temporal de fallo de INSERT en la BD descartable para comprobar 503 y
rollback real. El trigger append-only original de auditoría no se modifica.

## Migración y ejecución

La nueva revisión `0005_email_ingestion` depende de `0004_organizational_context`;
crea únicamente emails, su UNIQUE e índice cronológico en public. 0001–0004 no se
editan, n8n queda fuera de alcance y no hay migración automática al arrancar web.

```bash
# Desde backend/, con PostgreSQL de desarrollo iniciado:
uv run alembic upgrade head
uv run alembic check

# En Docker, después de reconstruir backend:
docker compose exec backend alembic upgrade head
```

Downgrade a 0004 elimina los emails; el ciclo head → 0004 → head y head → base →
head se prueba solo en PostgreSQL descartable. Sigue [persistencia](persistence.md#pruebas-de-integración)
para configurar TEST_DATABASE_URL y ejecutar `uv run pytest` desde backend/.

Los `.eml` sintéticos de tests cubren texto, HTML, multipart, charsets, headers,
attachments y rechazos. El corpus normalizado se explica en [dataset](dataset.md).

Pendiente: conectores Gmail/Graph/IMAP, integración n8n y su autenticación machine-to-
machine, reconstrucción de hilos, análisis de attachments y frontend. Fase 5 añade
detector, similitud, scoring, clasificación y LLM en endpoints separados; sin alertas.
