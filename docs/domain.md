# Dominio mínimo

Estas definiciones son conceptuales de Fase 0. No implican tablas, endpoints CRUD,
autenticación ni reglas implementadas. Los identificadores futuros serán UUID y
las fechas se intercambiarán como ISO 8601 con zona horaria, normalizadas a UTC.

## Conceptos

| Concepto | Definición y datos previstos |
| --- | --- |
| User | Persona que accede al sistema: identificador, nombre, correo y rol. La estrategia de autenticación queda pendiente. |
| Role | Responsabilidad de un usuario. Para el alcance inicial se prevé un rol por usuario; la autorización aún no existe. |
| ExecutiveContact | Ejecutivo conocido: identificador, nombre, cargo, correos y dominios legítimos. Aporta contexto para reconocer suplantaciones. |
| Vendor | Proveedor conocido: identificador, razón social, contactos y dominios legítimos. El tratamiento de cuentas bancarias se definirá cuando se implemente su gestión. |
| Email | Correo normalizado para análisis: identificador, remitente, destinatarios, asunto, texto y fecha de recepción. Su parser y mecanismo de ingestión son futuros. |
| EmailAnalysis | Ejecución de análisis de un Email: identificador, referencia al correo, fecha, versión del analizador y resultado neutral `BECAnalysisResult`. Un correo podrá tener varios análisis. |
| BECAlert | Caso para revisión humana asociado a un análisis: identificador, estado, responsable opcional y fechas. Su creación dependerá de una política futura, no de todo análisis automáticamente. |
| AuditLog | Registro de una acción relevante: identificador, actor humano o sistema, acción, recurso afectado y fecha. No debe copiar secretos ni cuerpos completos de correos. |

Relaciones principales: User tiene Role; Email tiene EmailAnalysis; BECAlert
referencia EmailAnalysis y opcionalmente User como responsable; AuditLog permite
rastrear acciones sobre estos recursos. ExecutiveContact y Vendor aportan contexto
al análisis, sin exigir que todo remitente esté previamente registrado.

## Enumeraciones previstas

### RiskLevel

`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`.

Categorías de riesgo del análisis. No se fijan aún umbrales ni se interpreta el
score como probabilidad estadística. La política de conversión se definirá junto
al motor y se versionará para conservar trazabilidad.

### AlertStatus

| Valor | Significado |
| --- | --- |
| OPEN | Alerta creada, pendiente de revisión. |
| UNDER_REVIEW | Un analista está evaluando el caso. |
| CONFIRMED_BEC | La revisión humana confirma fraude BEC. |
| FALSE_POSITIVE | La revisión humana descarta el fraude. |
| CLOSED | Caso cerrado administrativamente. |

El cierre no debe borrar el resultado de la revisión ni su auditoría. La matriz
de transiciones y sus permisos quedan pendientes; no hay máquina de estados aún.

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

Estos roles son una definición inicial de responsabilidades, no RBAC funcional.
