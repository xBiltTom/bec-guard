# Reportes operativos

Los reportes pertenecen al producto y consultan únicamente datos persistidos en
PostgreSQL. No importan el dataset, no leen ground truth y no llaman al evaluador
académico. La evaluación de holdout tiene metodología y resultados separados en
[evaluation.md](evaluation.md).

## API y permisos

| Ruta | Permiso | Descarga |
| --- | --- | --- |
| `GET /api/reports/operational.pdf` | ADMIN, MANAGER, AUDITOR | `application/pdf` |
| `GET /api/reports/operational.xlsx` | ADMIN, MANAGER, AUDITOR | XLSX Open XML |

ANALYST recibe 403. Ambas rutas requieren el JWT humano actual; la automation key
no concede acceso. `from_date` y `to_date` son filtros opcionales `YYYY-MM-DD`,
interpretados como días UTC inclusivos. Fechas invertidas responden 400. Se usa
`ingested_at` para correos, `analyzed_at` para análisis y `created_at` para alertas.
Sin fechas, se consideran todos los datos.

Los agregados incluyen total de emails, análisis completos y errores, distribución
de riesgo, tipo BEC, alertas por estado y veredictos. La lista de alertas solo contiene
ID, fecha de creación, score, risk level, tipo, estado, veredicto y nombre de la
persona asignada. Los estados y veredictos de alertas son sus valores actuales; no
se conserva una historia temporal para reconstruirlos como estaban al cierre de un
periodo.

Las respuestas usan `Content-Disposition: attachment` con nombre estable
`bec-guard-operational-YYYYMMDD.pdf` o `.xlsx`, añaden `Cache-Control: no-store` y
`X-Content-Type-Options: nosniff`. Los archivos se generan como bytes en memoria y
no se guardan en disco ni en una tabla.

## Contenido y privacidad

El PDF presenta cabecera, periodo, fecha UTC de generación, resumen, distribuciones,
tabla de alertas y la nota: “Los scores representan una evaluación del sistema y no
probabilidades de fraude.” El XLSX contiene las hojas `Resumen`, `Distribución de
riesgo`, `Tipos BEC` y `Alertas`; fechas y números conservan sus tipos de celda. No
hay macros.

Los formatos nunca consultan ni incluyen cuerpo, subject, remitente, destinatarios,
headers de autenticación, reply-to, return-path, referencia bancaria, prompts,
respuesta cruda del proveedor, AuditLog, contraseñas, JWT, API keys o etiquetas de
evaluación. Los textos de XLSX se guardan como celdas de texto, no fórmulas. HTML del
PDF se escapa y el renderer rechaza la carga de recursos externos.

## Implementación

`operational_summary.py` comparte las consultas de agregación con el dashboard.
`reporting.py` prepara una estructura transitoria y selecciona solamente los campos
de alerta autorizados. `report_formats.py` genera PDF mediante WeasyPrint 70 y XLSX
mediante openpyxl 3.1.5. El backend instala las bibliotecas Pango/HarfBuzz y DejaVu
que WeasyPrint requiere en Linux. No se incorpora un servicio de reporting aparte ni
se persiste un historial de exportaciones.
La imagen usa `XDG_CACHE_HOME=/tmp` para que Fontconfig disponga de una caché
temporal escribible como usuario no root; esa caché no almacena los reportes.

La UI `/reports` es visible para ADMIN, MANAGER y AUDITOR. El helper de descarga
envía `Authorization: Bearer` desde `sessionStorage`, lee el blob y usa una URL
temporal que revoca después de descargar. Un 401 limpia la sesión; un 403 muestra
permisos insuficientes y mantiene la sesión. Las fechas inválidas se detectan antes
de pedir el archivo y también se validan en backend.

Las pruebas cubren autorización, fechas, límites UTC, base vacía, agregados,
Content-Type/Disposition, archivo PDF y workbook XLSX, valores y hojas, protección
contra fórmulas y ausencia de datos privados. Las descargas frontend prueban header
de autorización, permisos, errores y revocación de URL.

## Límites

Los reportes reflejan el estado actual de las alertas y se calculan sin caché. Las
consultas no representan un snapshot histórico de cambios de estado y no ofrecen
comparaciones, filtros por usuario, reportes configurables ni envío programado.
La respuesta se construye en memoria, por lo que el tamaño práctico depende del
volumen operativo; el MVP no implementa exportaciones asíncronas ni almacenamiento
de archivos.
