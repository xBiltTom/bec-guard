# Dominio mínimo

Estas definiciones parten de Fase 0. User, Role, AuditLog, ExecutiveContact, Vendor
y Email/EmailAnalysis tienen persistencia. Hay autenticación, RBAC, contexto
organizacional, ingestión, análisis BEC híbrido y BECAlert automática persistente.
Los identificadores son UUID y las fechas se intercambiarán como ISO 8601 con zona horaria, normalizadas a UTC.

## Conceptos

| Concepto | Definición y datos previstos |
| --- | --- |
| User | Identidad autenticable con id, name, email normalizado, password_hash Argon2id, role, is_active y timestamps. Exactamente un rol por usuario, consultado desde DB al autorizar. |
| Role | Enum Python persistido como texto con CHECK. Cada usuario tiene un único rol; require_roles aplica RBAC sobre su rol actual. |
| ExecutiveContact | Ejecutivo conocido persistente: UUID, name, position, department nullable, un email legítimo normalizado, is_active y timestamps. Su dominio se podrá derivar del email. |
| Vendor | Proveedor conocido persistente: UUID, name, un domain principal canónico, contact_email y bank_account_reference opcionales, is_active y timestamps. Referencia bancaria opaca, nunca auditada. |
| Email | Correo persistente normalizado: UUID, Message-ID único, thread_id opcional, remitente, Reply-To, Return-Path, destinatarios JSONB, asunto, body_text, Authentication-Results, received_at e ingested_at. Sin análisis ni labels de evaluación. |
| EmailAnalysis | Análisis actual de un Email, máximo uno por UNIQUE email_id: status COMPLETED/ERROR, scores, riesgo/tipo nullable, señales JSONB, resumen/recomendación, proveedor/modelo, versión, error_code y fecha. Sin raw output ni prompt. |
| BECAlert | Alerta persistente, máximo una por análisis: UUID, analysis_id UNIQUE/FK RESTRICT, status OPEN inicial, verdict null, assigned_to FK RESTRICT nullable, resolution nullable, created_at/updated_at y closed_at nullable. alert-v1 crea solo para COMPLETED >=70; Fase 7 implementa claim/release/resolve humanos. |
| AuditLog | Registro persistente append-only con UUID, actor nullable, snapshot de rol, acción, recurso nullable, IP nullable, details JSONB mínimos y fecha. Un trigger impide UPDATE/DELETE. Audita auth, cambios de contexto e ingestión sin contenido del email. Nunca copia passwords, hashes, JWT, referencias bancarias ni cuerpos de correo. |

Relaciones principales: User tiene exactamente un Role; Email tiene EmailAnalysis; BECAlert
referencia EmailAnalysis y opcionalmente User como responsable; AuditLog permite
rastrear acciones sobre estos recursos. ExecutiveContact y Vendor aportan contexto
al análisis, sin exigir que todo remitente esté previamente registrado.

## User persistente (Fase 2A)

La tabla `public.users` usa UUID v4 generado por la aplicación al insertar.
`email` es obligatorio y único; `name`, `password_hash` y `role` también son
obligatorios. `is_active` es obligatorio y tiene default `true`.

`created_at` y `updated_at` son timestamps con zona horaria, generados por
PostgreSQL. Las conexiones del backend usan UTC. SQLAlchemy actualiza `updated_at`
cuando modifica la fila; `created_at` se conserva. Los detalles y las limitaciones
de escrituras SQL directas se describen en [persistencia](persistence.md).

Fase 2B genera/verifica password_hash con Argon2id y política de 12–128 caracteres.
Email se normaliza con trim + lowercase; un índice UNIQUE sobre lower(email)
impide duplicados por casing incluso mediante SQL directo. No hay registro público:
solo un CLI interactivo para el primer ADMIN. Ver [autenticación](authentication.md).

## Contexto organizacional persistente (Fase 3)

ExecutiveContact y Vendor usan UUID v4, timestamps con timezone/UTC y actualización
mediante SQLAlchemy, igual que User. La API normaliza textos; emails con trim +
lowercase y dominios con trim + lowercase sin punto final. Índices UNIQUE sobre
lower(email) y lower(domain) protegen identidades incluso mediante SQL directo.
Solo se desactivan con is_active; no hay hard delete ni se reutiliza una identidad
inactiva. Todos los roles leen; ADMIN y MANAGER crean/modifican. Los cambios y su
AuditLog se confirman atómicamente. Los lookups internos devuelven coincidencias
activas exactas por defecto, sin análisis BEC. Detalles, límites y contratos en
[contexto organizacional](organizational-context.md).

## Email persistente (Fase 4)

`public.emails` conserva evidencia normalizada sin raw MIME ni attachments.
Message-ID es obligatorio y único exacto, sin lowercase; emails/destinatarios se
validan y normalizan con trim/lowercase. received_at requiere zona horaria y se
normaliza a UTC; ingested_at lo genera PostgreSQL. UUID v4 desde aplicación.
No hay edición o eliminación por API. ADMIN/MANAGER/ANALYST ingieren, todos leen.
La inserción comparte commit con EMAIL_INGESTED, cuya auditoría no contiene datos
del mensaje. Parser, límites y contratos en [ingestión](email-ingestion.md).

El [dataset](dataset.md) separa label, split y expected_bec_type de la entrada
normalizada: son anotaciones de evaluación, no columnas ni resultados del detector.
Fase 5 consume únicamente el Email y contexto activo; no introduce anotaciones
de evaluación en el modelo. Fase 6 añade alertas sin cambiar scoring ni dataset.

## EmailAnalysis persistente (Fase 5)

`public.email_analysis` referencia emails con FK RESTRICT y UNIQUE email_id.
Guarda UUID, status, deterministic_score, semantic_score/risk_score/risk_level/
bec_type nullable, signals JSONB, summary/recommended_action nullable, provider/
model nullable, policy_version, error_code nullable y analyzed_at UTC. La revisión
0006 añade únicamente esta tabla; no cambia 0001–0005 ni n8n.

COMPLETED requiere scores semántico/final, nivel, resumen y recomendación.
ERROR conserva señales locales y deterministic_score, pero nunca tiene score
final, nivel o tipo. Puede reintentarse sobre la misma fila; COMPLETED se reutiliza.
El resultado y su evento de auditoría se confirman en la misma transacción.
Políticas, reglas, privacidad y API: [análisis BEC](bec-analysis.md).

## BECAlert persistente (Fase 6)

`public.bec_alerts`, migración 0007 sobre 0006. Política alert-v1: COMPLETED con
risk_score>=70 crea una alerta OPEN con verdict null. ERROR no genera alerta,
independientemente del score determinista. UNIQUE analysis_id, FK RESTRICT a
EmailAnalysis y User asignado; sin cascadas destructivas. OPEN exige closed_at null.
El índice created_at DESC/id sirve al listado sin filtros complejos.

La alerta y BEC_ALERT_CREATED comparten transacción con el análisis exitoso.
Análisis COMPLETED antiguos recuperan alertas faltantes al solicitar analyze;
sin backfill masivo. No hay PATCH/DELETE; claim/release/resolve añaden revisión humana.
Automatización usa actor/rol null en eventos de email/análisis/alerta; humanos
conservan su User/rol. [Contratos y orquestación](alerts-and-orchestration.md).

## Evaluación académica y reportes operativos (Fase 8)

La evaluación formal usa contratos Pydantic locales fuera de SQLAlchemy. `split`
solo selecciona los casos. `label`, `expected_bec_type` e `is_hard_negative` se
consultan después de obtener cada predicción; ninguno es un dato de producción. No hay
tabla, endpoint ni persistencia de corridas. El holdout se midió una vez con el
detector congelado, sin tuning posterior ([metodología](evaluation.md)).

`OperationalReport` es una estructura temporal formada desde PostgreSQL. PDF y
XLSX se generan en memoria para cada solicitud; no crean otra entidad, historial,
ni copia del cuerpo del correo. [Campos y privacidad](reporting.md).

## Enumeraciones previstas

### RiskLevel

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

Categorías implementadas por hybrid-v1: 0–39 LOW, 40–69 MEDIUM, 70–84 HIGH,
85–100 CRITICAL. Score no es probabilidad estadística. La versión completa
almacenada es det-v1/semantic-v1/hybrid-v1.

### AlertStatus

Representa únicamente el ciclo de vida operativo de la alerta.

| Valor | Significado |
| --- | --- |
| OPEN | Alerta creada y todavía no revisada. |
| UNDER_REVIEW | Un analista está revisándola. |
| CLOSED | La alerta ya no requiere trabajo activo. |

### AlertVerdict

Representa el resultado de la revisión humana, independiente del estado operativo.

| Valor | Significado |
| --- | --- |
| CONFIRMED_BEC | La revisión humana confirma fraude BEC. |
| FALSE_POSITIVE | La revisión humana descarta el fraude. |

Mientras no exista una decisión humana, `verdict = null`; no se añade `PENDING`.
Resolver asigna simultáneamente CLOSED y un veredicto, conservando su auditoría.
CLOSED por sí solo no distingue entre fraude confirmado y falso positivo.

Ejemplos válidos:

| status | verdict |
| --- | --- |
| OPEN | `null` |
| UNDER_REVIEW | `null` |
| CLOSED | CONFIRMED_BEC |
| CLOSED | FALSE_POSITIVE |

La migración 0008 exige OPEN sin responsable/veredicto/resolución/closed_at;
UNDER_REVIEW con responsable y los otros tres null; CLOSED con los cuatro presentes.
OPEN → claim → UNDER_REVIEW → resolve → CLOSED; release vuelve a OPEN.
No hay reopen. ANALYST opera su asignación; ADMIN/MANAGER supervisan otras;
AUDITOR es lector. La resolución es texto trim de 1–2000 caracteres y no se copia
a AuditLog. Claim/release/resolve usan bloqueo de fila y auditoría atómica;
repeticiones sin cambio no duplican eventos. Ver [frontend](frontend.md).

### BECType

| Valor | Significado |
| --- | --- |
| EXECUTIVE_IMPERSONATION | Suplantación de un ejecutivo. |
| VENDOR_FRAUD | Fraude mediante suplantación de proveedor. |
| BANK_ACCOUNT_CHANGE | Solicitud fraudulenta de cambio de cuenta. |
| SENSITIVE_DATA_REQUEST | Solicitud sospechosa de información sensible. |
| OTHER | Otro patrón BEC identificado. |

Un resultado tendrá un tipo principal o `null` si no se identifica un patrón;
`OTHER` no significa “correo legítimo”. Las señales podrán describir patrones
adicionales sin introducir nuevas categorías en esta fase.

### Role

| Valor | Responsabilidad futura |
| --- | --- |
| ADMIN | Administrar configuración, usuarios y contexto organizacional. |
| ANALYST | Investigar alertas y registrar decisiones de revisión. |
| MANAGER | Supervisar casos y consultar el estado agregado de riesgo. |
| AUDITOR | Consultar evidencia y trazabilidad con acceso de solo lectura. |

Para el MVP, cada User tendrá **exactamente un único Role**, entre ADMIN,
ANALYST, MANAGER y AUDITOR. Es un diseño RBAC con un rol por usuario; la
implementación de Fase 2A usa el campo `role` directamente en User.
No existe una relación `user_roles` en el diseño del MVP y múltiples roles
por usuario quedan fuera de alcance.

Si el proyecto crece y lo necesita, el modelo podrá migrar posteriormente a
una relación many-to-many. Esa alternativa no forma parte del diseño activo
de Fase 2. Role se implementa como enum Python y columna de texto con un CHECK;
no se crea un tipo enum nativo PostgreSQL. RBAC es una dependencia reutilizable;
los permisos de entidades futuras se definirán cuando existan esas funciones.
