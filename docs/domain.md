# Dominio mínimo

Estas definiciones parten de Fase 0. En Fase 2A solo User y Role tienen persistencia
implementada; los demás conceptos siguen siendo futuros. No hay endpoints CRUD,
autenticación ni reglas implementadas. Los identificadores son UUID y
las fechas se intercambiarán como ISO 8601 con zona horaria, normalizadas a UTC.

## Conceptos

| Concepto | Definición y datos previstos |
| --- | --- |
| User | Persona prevista para acceder al sistema. Ya se persisten id, name, email, password_hash, role, is_active, created_at y updated_at. Exactamente un rol por usuario; autenticación pendiente de Fase 2B. |
| Role | Enum Python persistido como texto con CHECK en users.role. Cada usuario tiene un único rol; la autorización aún no existe. |
| ExecutiveContact | Ejecutivo conocido: identificador, nombre, cargo, correos y dominios legítimos. Aporta contexto para reconocer suplantaciones. |
| Vendor | Proveedor conocido: identificador, razón social, contactos y dominios legítimos. El tratamiento de cuentas bancarias se definirá cuando se implemente su gestión. |
| Email | Correo normalizado para análisis: identificador, remitente, destinatarios, asunto, texto y fecha de recepción. Su parser y mecanismo de ingestión son futuros. |
| EmailAnalysis | Ejecución de análisis de un Email: identificador, referencia al correo, fecha, versión del analizador y resultado neutral `BECAnalysisResult`. Un correo podrá tener varios análisis. |
| BECAlert | Caso para revisión humana asociado a un análisis: identificador, estado operativo `status` (AlertStatus), veredicto humano `verdict` (AlertVerdict o `null`), responsable opcional y fechas. Su creación dependerá de una política futura, no de todo análisis automáticamente. |
| AuditLog | Registro de una acción relevante: identificador, actor humano o sistema, acción, recurso afectado y fecha. No debe copiar secretos ni cuerpos completos de correos. |

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

`password_hash` es únicamente almacenamiento requerido de un hash futuro: no se
implementan hashing, verificación de contraseñas ni autenticación hasta Fase 2B.
La normalización de email a minúsculas se definirá antes de exponer altas de
usuarios; la unicidad actual compara el texto exacto, sin normalización automática.

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
no se crea un tipo enum nativo PostgreSQL ni RBAC funcional.
