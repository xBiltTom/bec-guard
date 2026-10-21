# Evaluación formal congelada - eval-v1

Evaluación académica del baseline determinista, ejecutada **una vez** el
2026-10-21 a las 15:21:51 UTC. El corpus es sintético: **42 casos holdout, 30
legítimos y 12 BEC**, incluidos 9 hard negatives legítimos. No es un benchmark
real-world ni permite afirmar rendimiento productivo. Development (98 casos)
se usó antes para desarrollar el motor; holdout permaneció reservado hasta el freeze.

## Freeze y procedencia

Antes de ejecutar: 451 tests backend aprobados con PostgreSQL 18, Ruff check y
format --check aprobados, validador estructural y regression development aprobados.
Detector y dataset con diff vacío respecto a Fase 7. No había cambios rastreados
pendientes; skills-lock.json preexistente permaneció sin seguimiento.

| Dato | Valor |
| --- | --- |
| Git SHA evaluado | `71f5697312072c106730dbc5d594f5ab11816bb5` |
| Dataset SHA-256 | `1a62cf39afbd8f7c59ecb7b7d2f25c78826e92df9a5425aa39f0fcf8e1460979` |
| Context SHA-256 | `32e2e91b5827abf3ad84db43e4d99e7bfec903f4cc8b3b28cccb134ae75b69ff` |
| Políticas | det-v1 / semantic-v1 / hybrid-v1 / alert-v1 |
| Detección | score >=40 |
| Alerta operativa | score >=70, importado de ALERT_THRESHOLD |
| Niveles vigentes | LOW 0–39, MEDIUM 40–69, HIGH 70–84, CRITICAL 85–100 |
| Proveedor / modelo | null / null; baseline sin LLM |
| Completados / errores / coverage | 42 / 0 / 100% |

El CLI escribió freeze.json antes de predecir, con versiones, commit, hashes del
corpus/contexto y de siete archivos del detector. Resultados locales ignorados:
`artifacts/evaluation/20261021T152151453992Z-4506b4d1/` contiene freeze.json,
result.json, predictions.json y hybrid-status.json (NOT_RUN). No se versionan
predicciones por caso ni correos.
En esta documentación solo se registran agregados; no se inspeccionaron cuerpos
fallidos para diseñar reglas. **No hubo tuning post-holdout ni cambios del dataset.**

## Detección >=40

| | Real BEC | Real legítimo |
| --- | ---: | ---: |
| Predicción BEC | TP 10 | FP 0 |
| Predicción legítimo | FN 2 | TN 30 |

| Métrica | Resultado |
| --- | ---: |
| Precision | 100.00% |
| Recall / sensibilidad | 83.33% |
| F1 | 90.91% |
| Accuracy | 95.24% |
| Specificity | 100.00% |
| False positive rate | 0.00% |

El baseline identifica diez ataques bajo este criterio, pero omite dos. Precision
100% describe diez predicciones positivas sin FP en este pequeño corpus; no indica
que el motor sea infalible. El conjunto no mide todas las formas de fraude real.

## Alerta operativa >=70

| | Real BEC | Real legítimo |
| --- | ---: | ---: |
| Predicción BEC | TP 0 | FP 0 |
| Predicción legítimo | FN 12 | TN 30 |

| Métrica | Resultado |
| --- | ---: |
| Precision | Indefinida (null: no hubo predicciones positivas) |
| Recall / sensibilidad | 0.00% |
| F1 | 0.00% |
| Accuracy | 71.43% |
| Specificity | 100.00% |
| False positive rate | 0.00% |

Subir de 40 a 70 reduce los TP de diez a cero sin reducir FP (ya eran cero).
El baseline determinista por sí solo no alcanza el umbral operativo en ninguno de
los doce ataques reservados. Accuracy 71.43% refleja los treinta negativos; oculta
el fallo de sensibilidad si se interpreta aisladamente. Esto no es una evaluación
del pipeline híbrido productivo: falta el score semántico real.

## Hard negatives y tipos

Hard negatives: **9**, completados9/errores0, FP detección0 y FP alerta0; FPR0%
en ambos criterios. Un cero observado en nueve ejemplos no demuestra una FPR
poblacional nula. Las tasas usan hard negatives COMPLETED como denominador;
si hubiese ERROR se mostrarían por separado, sin contarlos como negativos.

Tipos en los doce ground-truth BEC, usando la sugerencia natural del determinista
independientemente del threshold binario: **8/12 correctos, type accuracy66.67%**.
No se inventan tipos semánticos para el baseline.

| Tipo esperado | Total | Correctos | Incorrectos | No clasificados |
| --- | ---: | ---: | ---: | ---: |
| EXECUTIVE_IMPERSONATION | 4 | 4 | 0 | 0 |
| VENDOR_FRAUD | 3 | 3 | 0 | 0 |
| BANK_ACCOUNT_CHANGE | 2 | 1 | 1 | 0 |
| SENSITIVE_DATA_REQUEST | 2 | 0 | 2 | 0 |
| OTHER | 1 | 0 | 0 | 1 |

Estos subgrupos de uno a cuatro casos solo permiten descripción; no conclusiones
estadísticas fuertes ni comparaciones generales entre categorías.

## Latencia y definiciones

Determinista local: media **0.601490 ms**, mediana **0.485375 ms**, p95
**1.015705 ms**. Medida con perf_counter por caso; excluye carga de corpus/contexto,
serialización, HTTP y PostgreSQL. p95 usa nearest rank (ceil(0.95*n)). Depende del
hardware y carga del equipo; no es SLA ni requisito de CI. No se repitió holdout
para optimizar o estabilizar tiempos.

Precision=TP/(TP+FP), recall=TP/(TP+FN), F1=2TP/(2TP+FP+FN),
accuracy=(TP+TN)/N, specificity=TN/(TN+FP), FPR=FP/(FP+TN). División por cero devuelve
null, nunca NaN. Las matrices usan únicamente casos COMPLETED; coverage reporta su
proporción sobre todos los seleccionados. Effective recall=TP/total ground-truth BEC
incluye ERROR como no detectado en ese denominador; aquí coincide con recall.
Los errores no se convierten en LEGITIMATE ni score cero.

## Evaluación híbrida: NOT_RUN

**Reason: real external LLM evaluation requires explicit user authorization.**
No se llamó OpenAI, Gemini ni Groq aunque pudiera existir una key local. No hay
métricas híbridas de calidad inventadas con fakes. Los fakes solo prueban contratos,
coverage, errores y la reutilización de combine_scores/resolve_bec_type productivos.

El runner híbrido usa exactamente reglas/contexto, SemanticAnalyzer y scoring de
producción; no tiene otro prompt, temperatura o clasificador. Un futuro experimento
real autorizado deberá guardar nuevo freeze/provider/model. El resultado no será
independiente de esta primera observación del corpus y debe identificarse como otro
experimento; no se debe tunear contra estos resultados y presentarlo como holdout
intacto. Si se descubre un bug objetivo del detector se detienen nuevas evaluaciones
hasta documentar una nueva metodología, sin ajustes silenciosos.

## CLI y separación del producto

Desde backend/, la confirmación es obligatoria. La ejecución realizada fue:

```bash
uv run python -m app.scripts.evaluate_holdout \
  --mode deterministic --confirm-holdout \
  --output-dir ../artifacts/evaluation
```

Solo tras autorización explícita de gasto, la futura ejecución híbrida añade:
`--mode hybrid --confirm-holdout --allow-external-llm`. Sin ambas banderas no se
inicializa proveedor. El evaluador solo pasa case.email y contexto al detector;
anotaciones se leen después de obtener la predicción. No escribe DB ni ofrece HTTP.
CI prueba métricas con fixtures artificiales; no ejecuta holdout formal.
Los reportes operativos PDF/XLSX solo leen PostgreSQL y nunca importan este tooling.
