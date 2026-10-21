# Análisis BEC — Fase 5

El backend analiza un Email persistido y conserva un EmailAnalysis actual. Es un
monolito síncrono: reglas + contexto activo → semántica LangChain → scoring híbrido
→ resultado y auditoría en un commit. Fase 6 añade BECAlert OPEN para COMPLETED
>=70 en esa misma transacción, sin ejecutar recomendaciones.

## Motor determinista (`det-v1`)

`assess_deterministically(email, context)` es puro. `load_analysis_context(session)`
consulta ejecutivos y proveedores activos en PostgreSQL. Los lookups exactos de
Fase 3 conservan su contrato; el motor necesita además comparar nombres/dominios.
Solo el contexto activo participa. No se consulta DNS ni se verifica DKIM.

| Señal | Fuente | Contribución |
| --- | --- | --- |
| EXECUTIVE_IDENTITY_MISMATCH | CONTEXT | 35 con dominio desconocido; 15 con dominio registrado. |
| EXECUTIVE_DOMAIN_LOOKALIKE | CONTEXT | 25 |
| VENDOR_IDENTITY_MISMATCH | CONTEXT | 30 |
| VENDOR_DOMAIN_LOOKALIKE | CONTEXT | 25 |
| REPLY_TO_MISMATCH | RULE | 15 entre dominios; 3 entre direcciones del mismo dominio. |
| RETURN_PATH_MISMATCH | RULE | 4 por dominio distinto. |
| SPF_FAIL / DKIM_FAIL / DMARC_FAIL | RULE | 8 / 8 / 18 |
| PAYMENT_REQUEST | RULE | 8 |
| BANK_ACCOUNT_CHANGE | RULE | 24 |
| SENSITIVE_DATA_REQUEST | RULE | 22 |
| URGENCY | RULE | 8, únicamente junto a una solicitud de pago, cambio bancario o datos. |
| AUTHORITY_PRESSURE | RULE | 10, únicamente junto a una solicitud relevante. |
| SECRECY_REQUEST | RULE | 12 por evitar verificación, registro o consulta independiente. |

Cada código aparece como máximo una vez. El score es `min(100, suma de
contribution)`, sin parámetros aprendidos ni bonus ocultos. Por el límite, la suma
de contribuciones puede superar el score. Las descripciones son plantillas cortas,
sin copiar fragmentos del correo. Dominio desconocido por sí solo no genera riesgo.

Nombres: comparación por tokens completos, lowercase y sin acentos; se admiten
títulos/tokens adicionales. Para ejecutivos se requieren al menos dos tokens
conocidos y email distinto; un primer nombre aislado no basta. Un email ejecutivo
oficial no produce suplantación por sí mismo. Un dominio exacto de proveedor o
su contact_email registrado se reconoce como legítimo para estos checks, incluso
si el contacto externo usa otro dominio. Cambiar de persona dentro del dominio
oficial no genera mismatch. Esto no descarta una cuenta comprometida.

Similitud de dominios: hostnames ASCII/punycode, lowercase y sin punto final.
Se exige igual número de labels y exactamente uno distinto, con longitud mínima
5 en ambos lados. Ese label debe tener distancia Levenshtein 1 o equivalencia
visual ASCII `rn`/`m`. `ernpresa.example` puede parecerse a `empresa.example`;
compartir `.example` no hace lookalike a `otroproveedor` y `proveedor`.
No hay public suffix list, Unicode confusable analysis ni detección exhaustiva de
subdominios abusivos, transposiciones o sustituciones de TLD cortos.

Authentication-Results solo interpreta tokens explícitos `spf=fail`, `dkim=fail`,
`dmarc=fail`, sin confundir softfail con fail. Pass no reduce el score ni certifica
legitimidad; la cabecera almacenada tampoco es una validación independiente.
Return-Path tiene peso bajo porque puede pertenecer a infraestructura legítima.
Reply-To null o idéntico no genera señal.

El contenido usa regex/frases modestas en español e inglés. Se excluyen cláusulas
negadas de solicitudes de pago/cambio/datos; las solicitudes de evitar controles
se buscan también en cláusulas negativas. No es NLP avanzado: hay negaciones,
paráfrasis, mensajes reenviados y solicitudes sutiles que se pueden interpretar mal.
Urgencia o confidencialidad ordinarias no equivalen a BEC.

## Análisis semántico (`semantic-v1`)

`SemanticAnalyzer` crea un único chat model mediante `create_chat_model(settings)`
y llama `with_structured_output(SemanticAssessment, method="json_schema")`.
Se usan langchain-core y los adaptadores mantenidos langchain-openai,
langchain-google-genai y langchain-groq, fijados en uv.lock para Python 3.14.
No se instala LangGraph ni se construye un agente. No hay tools, memory ni RAG.

| Variable | Uso |
| --- | --- |
| LLM_PROVIDER | `openai`, `google` (alias `gemini`) o `groq`. |
| LLM_MODEL | ID del modelo seleccionado; obligatorio al analizar. Debe soportar JSON Schema nativo. |
| OPENAI_API_KEY | Solo para OpenAI. |
| GOOGLE_API_KEY | Solo para Gemini Developer API; se fuerza vertexai=False. |
| GROQ_API_KEY | Solo para Groq. |
| LLM_TIMEOUT_SECONDS | Default 30 segundos, entre 1 y 120; timeout del adaptador/HTTP. |

La configuración se lee al ejecutar el análisis, no al arrancar ni migrar.
Proveedor/modelo/key ausentes o configuración inválida producen ERROR. No hay un
modelo predeterminado ni fallback entre proveedores. SDK max_retries=0: el retry
de aplicación es un POST explícito. La disponibilidad y compatibilidad JSON Schema
del modelo elegido se deben comprobar en el proveedor; un modelo incompatible
produce error, nunca una interpretación libre de texto.

SemanticAssessment exige risk_score entero 0–100, bec_type nullable del catálogo,
hasta 8 señales SEMANTIC (code estable, descripción hasta 240 caracteres), summary
no vacío hasta 600 y recommended_action no vacía hasta 400. Rechaza campos extra,
fuentes distintas, scores boolean/string, textos vacíos y NUL. Se valida de nuevo
localmente; no se conserva la respuesta cruda.

El prompt distingue BEC de phishing/malware general y prohíbe inventar contexto.
Email se delimita como JSON de datos no confiables en un HumanMessage, separado
del SystemMessage. Las instrucciones dentro de cualquier campo se ignoran como
instrucciones del modelo. Se incluyen sender, reply-to, subject, body y hechos
derivados: coincidencias de identidad y señales técnicas/contextuales. No se
serializan entidades completas, usuarios, JWT, hashes, AuditLog ni credenciales.
Las referencias bancarias conocidas que aparezcan en los campos se redactan
localmente, incluso con distinto casing; no se envía bank_account_reference.
No se realiza todavía comparación bancaria específica.

Se desactiva LangSmith tracing durante la invocación, incluso si estaba activado
por entorno. La aplicación no registra prompt, body, key, respuesta ni excepciones
crudas del proveedor. No habilitar logs HTTP/SDK de depuración en un despliegue con
correos reales: esos diagnósticos pertenecen a dependencias externas.

La defensa ante prompt injection es básica: separación de mensajes, instrucción
fuerte, JSON delimitado, contrato estructurado y ausencia de herramientas/acciones.
Los fakes prueban la frontera y el contrato, no demuestran inmunidad semántica de
un modelo real. Solo el proveedor seleccionado recibe los datos del correo.

Referencias de integración: [ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai),
[Gemini](https://docs.langchain.com/oss/python/integrations/chat/google_generative_ai),
[Groq structured output](https://reference.langchain.com/python/langchain-groq/chat_models/ChatGroq/with_structured_output).

## Scoring híbrido (`hybrid-v1`)

`combine_scores` calcula 50% determinista + 50% semántico, con redondeo entero
half-up: `(deterministic_score + semantic_score + 1) // 2`. Única salvaguarda:
si el determinista es >=70, el resultado final tiene floor 70. Un LLM contradictorio
no borra evidencia local fuerte. No hay ML, entrenamiento ni calibración estadística.

| Score | RiskLevel |
| --- | --- |
| 0–39 | LOW |
| 40–69 | MEDIUM |
| 70–84 | HIGH |
| 85–100 | CRITICAL |

El motor determinista sugiere un tipo, en este orden cuando coexisten señales:
BANK_ACCOUNT_CHANGE, SENSITIVE_DATA_REQUEST, EXECUTIVE_IMPERSONATION, VENDOR_FRAUD.
El resultado final usa null bajo 40; desde 40 prefiere ese tipo local y, si no
existe, el sugerido por semántica. Si ninguno identifica patrón sigue null.
OTHER requiere una sugerencia semántica; no se usa como sinónimo de legítimo.
Las señales semánticas se normalizan a Signal con contribution=0: no tienen peso
aditivo propio, participan mediante semantic_score en la media.

## Persistencia, transacción y concurrencia

`public.email_analysis`, revisión nueva `0006_email_analysis` sobre 0005:
UUID, FK RESTRICT a emails, UNIQUE email_id, status, deterministic_score,
semantic_score/risk_score/risk_level/bec_type nullable, signals JSONB, summary,
recommended_action, provider, model, policy_version, error_code y analyzed_at UTC.
La versión almacenada es `det-v1/semantic-v1/hybrid-v1`. No hay índices adicionales
a PK y UNIQUE; la consulta real es por email_id. CHECKs validan enums, rangos,
forma array, thresholds y consistencia entre status y resultado.

No guarda prompt, raw output, key, copia del cuerpo ni labels del dataset.
Un Email tiene como máximo un análisis actual; no hay historial de ejecuciones.
COMPLETED se devuelve sin invocar LLM; Fase 6 recupera una alerta faltante cuando
corresponde y audita solo esa creación. Con alerta existente no repite auditoría. ERROR puede
reintentarse y actualiza el mismo UUID, recalculando con el contexto actual.
Un COMPLETED no se invalida al cambiar contexto/modelo/política: no existe endpoint
de reanálisis forzado en este MVP.

POST bloquea la fila padre Email con SELECT FOR UPDATE y después consulta el
análisis. Dos solicitudes del mismo email se serializan; UNIQUE protege además
la base. Correos distintos no comparten ese bloqueo. Se mantiene la transacción
durante el LLM: suficiente para el MVP, con coste de ocupación de conexión/worker.
Timeout es del transporte; no es un deadline global estricto para toda la petición.
Si una primera ejecución falla, otra solicitud pendiente puede efectuar el retry.

El análisis y EMAIL_ANALYZED o EMAIL_ANALYSIS_FAILED comparten un commit.
Actor, rol actual, tipo email_analysis, UUID del análisis, IP del peer directo y
timestamp; details=null. No se auditan scores, señales, subject, sender ni body.
Un fallo de auditoría revierte tanto creación como retry, conservando un ERROR
anterior cuando existe. Errores de persistencia responden 503 genérico.
El trigger append-only histórico permanece intacto.

Fase 6 añade BEC_ALERT_CREATED en la misma transacción para COMPLETED >=70.
Las llamadas de automatización reutilizan este servicio con actor null y una API
key acotada, sin sustituir RBAC/JWT humano. Ver [alertas y orquestación](alerts-and-orchestration.md).

## API y ERROR

| Ruta | Permiso | Resultado |
| --- | --- | --- |
| POST /api/emails/{email_id}/analyze | ADMIN, MANAGER, ANALYST | 200 COMPLETED; 502/503 ERROR persistido. AUDITOR recibe 403. |
| GET /api/emails/{email_id}/analysis | Todos los roles autenticados | 200 para COMPLETED o ERROR; 404 sin Email/análisis. |

Token ausente/inválido o usuario inactivo: 401. UUID inválido: 400. Email
inexistente: 404 antes de configurar LLM. RBAC usa siempre el User actual en DB.

| error_code | POST HTTP |
| --- | --- |
| LLM_NOT_CONFIGURED | 503 |
| LLM_TIMEOUT | 502 |
| LLM_PROVIDER_ERROR | 502 |
| LLM_INVALID_OUTPUT | 502 |

ERROR conserva deterministic_score y señales RULE/CONTEXT. semantic_score,
risk_score, risk_level, bec_type, summary y recommended_action quedan null;
**ERROR nunca significa LOW, LEGITIMATE ni score cero**. El POST de error devuelve
EmailAnalysisResponse completo sanitizado, igual que el GET posterior con HTTP 200.
Si falló la BD/auditoría se devuelve el 503 genérico de infraestructura, sin afirmar
que el ERROR se persistió. El contrato HTTP detallado está en [API](api-contracts.md).

## Regresión de development y límites

Desde backend/, sin PostgreSQL ni API keys:

```bash
uv run python -m app.scripts.validate_dataset
uv run python -m app.scripts.check_development
```

El loader heredado valida estructura/conteos del archivo completo. El harness
filtra `development` antes de leer labels para sus resúmenes o invocar motores;
solo `case.email` llega al motor. Usa el contexto sintético en memoria y no escribe
datos de prueba ni etiquetas en DB. Imprime agregados de scores/señales/errores,
sin cuerpos. No permite seleccionar holdout. `--llm` habilita explícitamente
llamadas externas con el proveedor configurado (98 posibles llamadas con coste);
sin esa bandera no llama LLM. En CI solo se usan reglas y fakes controlados.

Regresión local determinista: 98 development, legítimos 70 (0–26, media 3.83),
BEC 28 (15–90, media 62.64), los 21 hard negatives legítimos LOW. Distribución:
75 LOW, 12 MEDIUM, 7 HIGH, 4 CRITICAL. Es una comprobación de desarrollo, no
evaluación formal ni evidencia de rendimiento del pipeline con LLM real.
No se usó contenido ni labels holdout para diseñar, ajustar o evaluar el motor;
solo pasaron las validaciones estructurales heredadas. Dataset sin modificaciones.

Las reglas pueden omitir ataques sutiles; el peso 50/50 también puede dejar en
MEDIUM ataques detectados solo por semántica. El corpus es sintético y los scores
no son probabilidades calibradas. No hubo llamadas reales pagadas para esta fase:
no se afirma calidad ni disponibilidad de un modelo externo particular.
El cuerpo se envía sin truncarlo: modelos con contexto insuficiente pueden fallar.
Sin análisis de adjuntos, DNS ni conectores. Fase 6 implementa BECAlert automática
y orquestación Webhook n8n; Fase 7 añade frontend y revisión humana, sin cambiar
estas políticas ni ajustar scoring con dataset. Ver [frontend](frontend.md).
