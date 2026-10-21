# Dataset sintético controlado

`datasets/bec_eval.jsonl` contiene **140 casos ficticios** para desarrollo, regresión
y evaluación académica inicial. No son correos reales ni un benchmark representativo
del mundo real. No permiten afirmar precisión del futuro detector en producción.
Fase 5 implementó el motor y una regresión exclusiva de development. Fase 8 añadió
la evaluación determinista formal del holdout después de congelar el detector,
sin ajustes posteriores a partir de sus resultados.

## Conteos y separación

| Split | LEGITIMATE | BEC | Total |
| --- | --- | --- | --- |
| development | 70 | 28 | 98 |
| holdout | 30 | 12 | 42 |
| Total | 100 | 40 | 140 |

| expected_bec_type | development | holdout | Total |
| --- | --- | --- | --- |
| EXECUTIVE_IMPERSONATION | 8 | 4 | 12 |
| VENDOR_FRAUD | 7 | 3 | 10 |
| BANK_ACCOUNT_CHANGE | 6 | 2 | 8 |
| SENSITIVE_DATA_REQUEST | 4 | 2 | 6 |
| OTHER | 3 | 1 | 4 |

Los 100 legítimos incluyen **30 hard negatives** (21 development y 9 holdout):
urgencia, pagos y transferencias con aprobaciones, autoridad ejecutiva, facturas,
referencias bancarias conocidas, cambios administrativos verificados y
confidencialidad normal. Los otros 70 cubren proyecto, personal, sistemas, compras,
contabilidad y operaciones. No se presume que urgencia o confidencialidad sean BEC.
Los ataques incluyen suplantaciones y cambios de cuenta; algunos usan dominios
legítimos bajo el supuesto sintético de cuenta comprometida. SPF/DKIM/DMARC pass
no es un veredicto: hay Authentication-Results seleccionados en ambas clases.

`development` se utilizó para construir y revisar el detector. El detector quedó
congelado antes de una única evaluación formal determinista de holdout; sus resultados
no se utilizaron para modificar reglas, scoring ni datos. El holdout no debe usarse
para ajustes posteriores. La metodología y los resultados agregados están en
[evaluación](evaluation.md). Validar estructura/conteos no equivale a evaluar
efectividad. Es un split sintético inicial, no sustituye datos reales independientes
o temporales.

## Contexto ficticio

`datasets/context.json` declara la organización Luminaria Ficticia, cuatro ejecutivos
y cuatro proveedores con referencias `REF-FICTICIA-*`. Son únicamente contexto de
los escenarios. No se importan a PostgreSQL ni se crean usuarios automáticamente.
Todos los nombres/organizaciones se inventaron para este fixture y los dominios
son `.example`, reservados para ejemplos. No hay datos personales ni cuentas reales.

Se eligió `.example` para mantener la validación EmailStr existente. No se relaja
la política global de emails para aceptar dominios `.test`. Los Message-ID son
neutrales y no contienen la etiqueta; UUIDs, orden de filas y fechas no codifican
intencionadamente la clase. El contenido de cada escenario es distinto.

## Formato y prevención de leakage

Una línea JSON por caso, UTF-8:

```json
{
  "case_id": "CASE-001",
  "split": "development",
  "label": "LEGITIMATE",
  "expected_bec_type": null,
  "is_hard_negative": true,
  "email": {
    "message_id": "<sample@corpus.becguard.example>",
    "sender_email": "persona@luminaria.example",
    "to_recipients": ["finanzas@luminaria.example"],
    "subject": "Pago aprobado",
    "body_text": "Seguir la aprobación y referencia habituales.",
    "received_at": "2026-10-20T14:00:00Z"
  }
}
```

DatasetCase/DatasetLabel/ExpectedBECType son schemas de evaluación separados de
SQLAlchemy. `expected_bec_type` es null en legítimos y obligatorio con un valor
permitido en BEC. `is_hard_negative` solo puede marcar legítimos.

**Solo `case.email` es un EmailIngestRequest.** Nunca pasar `case.model_dump()` al
análisis o a la API. label, split, expected_bec_type e is_hard_negative no son
features de producción ni columnas de emails. El contrato HTTP rechaza estos
campos, así como bec_type, risk_score y verdict. No hay importación automática
ni persistencia de ground truth. Un loader no decide si el texto es fraudulento:
las etiquetas son anotaciones del diseño sintético de cada caso.

## Loader y CLI

`app.services.dataset.load_dataset(path)` devuelve DatasetCase validados y permite
obtener la entrada normalizada como `case.email`. No usa red ni PostgreSQL.
Comprueba filas, campos, identidades case_id/Message-ID únicas, labels/tipos,
conteos exactos por split/tipo y al menos 20 hard negatives. También rechaza emails
o URLs HTTP(S) con dominios no reservados en el corpus. Estas verificaciones no
pueden demostrar por sí solas que un nombre o todo texto libre sea ficticio; esa
propiedad se establece al crear y revisar los escenarios. Los tests verifican
además direcciones en el cuerpo y el contexto sintético.

Desde backend/, sin .env ni base de datos:

```bash
uv run python -m app.scripts.validate_dataset
# O un archivo explícito con el mismo formato/conteos:
uv run python -m app.scripts.validate_dataset ../datasets/bec_eval.jsonl
uv run pytest tests/test_dataset.py
```

Salida: únicamente total y conteos de labels, splits, tipos y hard negatives.
Un archivo inválido devuelve exit code 1 con error sin contenido del caso; no
imprime emails ni el dataset completo. Filas vacías o JSON inválido se rechazan.
La imagen de API no incorpora datasets/; utiliza el CLI en el checkout del host
o monta explícitamente el archivo y proporciona su ruta.

## Fixtures MIME y límites

`backend/tests/fixtures/mime/` contiene 15 `.eml` sintéticos independientes del
corpus: plain, alternative, HTML, UTF-8, Latin-1, headers seleccionados, attachments,
un Message-ID duplicado y casos inválidos de From/Reply-To/Date/Message-ID/charset.
Los límites de tamaño, cuerpo y estructura se prueban con mensajes generados en
memoria; no se versionan archivos gigantes. Ver [ingestión](email-ingestion.md).

No usar este fixture como dataset real-world ni importar su metadata como entrada
del detector. El runner formal de holdout es tooling académico local y no se expone
por HTTP ni persiste resultados en PostgreSQL.
`uv run python -m app.scripts.check_development` ejecuta reglas sobre
98 development con contexto sintético en memoria; `--llm` habilita llamadas externas
explícitas. No ofrece opción holdout ni persiste datos/labels. Solo imprime
agregados. Ver [regresión y límites](bec-analysis.md#regresión-de-development-y-límites).
