# Dominio mínimo

Estas definiciones parten de Fase 0. User, Role, AuditLog, ExecutiveContact, Vendor
y Email tienen persistencia. Hay autenticación, RBAC y gestión backend del contexto
organizacional e ingestión de emails. EmailAnalysis y BECAlert siguen siendo futuros,
sin reglas BEC.
Los identificadores son UUID y las fechas se intercambiarán como ISO 8601 con zona horaria, normalizadas a UTC.

## Conceptos

| Concepto | Definición y datos previstos |
| --- | --- |
| User | Identidad autenticable con id, name, email normalizado, password_hash Argon2id, role, is_active y timestamps. Exactamente un rol por usuario, consultado desde DB al autorizar. |
| Role | Enum Python persistido como texto con CHECK. Cada usuario tiene un único rol; require_roles aplica RBAC sobre su rol actual. |
| ExecutiveContact | Ejecutivo conocido persistente: UUID, name, position, department nullable, un email legítimo normalizado, is_active y timestamps. Su dominio se podrá derivar del email. |
| Vendor | Proveedor conocido persistente: UUID, name, un domain principal canónico, contact_email y bank_account_reference opcionales, is_active y timestamps. Referencia bancaria opaca, nunca auditada. |
| Email | Correo persistente normalizado: UUID, Message-ID único, thread_id opcional, remitente, Reply-To, Return-Path, destinatarios JSONB, asunto, body_text, Authentication-Results, received_at e ingested_at. Sin análisis ni labels de evaluación. |
| EmailAnalysis | Ejecución de análisis de un Email: identificador, referencia al correo, fecha, versión del analizador y resultado neutral `BECAnalysisResult`. Un correo podrá tener varios análisis. |
| BECAlert | Caso para revisión humana asociado a un análisis: identificador, estado operativo `status` (AlertStatus), veredicto humano `verdict` (AlertVerdict o `null`), responsable opcional y fechas. Su creación dependerá de una política futura, no de todo análisis automáticamente. |
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
No se implementan EmailAnalysis, motor BEC, scoring o alertas.

## Enumeraciones previstas

### RiskLevel

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

Categorías de riesgo del análisis. No se fijan aún umbrales ni se interpreta el
score como probabilidad estadística. La política de conversión se definirá junto
al motor y se versionará para conservar trazabilidad.

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

Mientras no exista una decisión humana, `verdict = null`; no se añade un valor
`PENDING`. El cierre administrativo cambia `status`, pero no borra ni reemplaza
el veredicto ni su auditoría. `CLOSED` por sí solo no determina un resultado.

Ejemplos válidos:

| status | verdict |
| --- | --- |
| OPEN | `null` |
| UNDER_REVIEW | `null` |
| CLOSED | CONFIRMED_BEC |
| CLOSED | FALSE_POSITIVE |

Los ejemplos no definen una matriz completa de combinaciones permitidas.
Las transiciones exactas, condiciones de cierre y permisos se definirán en
Fase 2. No se implementa una máquina de estados en esta minifase.

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
