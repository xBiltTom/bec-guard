# Aplicación operativa y revisión humana

React 19 + TypeScript + Vite, con React Router para navegación. CSS plano y
componentes pequeños compartidos; sin state manager, SDK generado, librería de
charts ni modo mock. El dashboard consume agregados reales; los botones principales
usan FastAPI. En desarrollo, Vite proxifica `/api` al backend igual que `/health`.
Compose usa `http://backend:8000`; nunca se expone una key LLM o de automatización.

## Acceso y sesión

Crear el primer ADMIN con el CLI interactivo existente (ver README). No hay registro,
CRUD de usuarios, refresh ni recuperación de contraseña. Abrir la aplicación y
usar ese correo/contraseña en `/login`. Login llama POST /api/auth/login y verifica
GET /api/auth/me antes de guardar únicamente el access token en sessionStorage.
La contraseña no se persiste. Al recargar se vuelve a validar /me; el JWT del backend
es la autoridad sobre expiración y rol actual. Un fallo temporal de /me permite
reintentar; un 401 limpia sesión y redirige a login. Logout elimina el token. Un 403
muestra falta de permisos y conserva sesión. Una respuesta antigua de /me no puede
restaurar un token eliminado mientras la petición estaba pendiente.

sessionStorage dura la pestaña y sigue siendo accesible a JavaScript del mismo
origen: no se afirma inmunidad ante XSS ni revocación de JWT tras logout. No hay
localStorage, cookies de sesión ficticias ni secretos en DOM/logs del cliente.

## Rutas y navegación

| Ruta | Contenido |
| --- | --- |
| /login | Acceso con correo y contraseña, loading y error genérico. |
| / | Dashboard: carga pendiente, estados, resultados humanos, riesgo, patrones, actividad UTC de siete días y alertas recientes. |
| /alerts | Cola con paginación, estado/riesgo/tipo y Mis alertas; filtros conservados en URL. |
| /alerts/:alertId | Riesgo, identidad, resumen, recomendación, señales por origen, correo plano y panel HITL. |
| /emails | Resumen sin cuerpos, paginación. |
| /emails/:emailId | Headers, body plano, análisis/manual retry y enlace a alerta cuando existe. |
| /executives | Consulta y mantenimiento de identidades legítimas. |
| /vendors | Consulta y mantenimiento de dominios/contactos y referencia bancaria en formulario/detalle. |
| /audit | Lectura ADMIN/AUDITOR, filtros action/resource_type y paginación. |
| /reports | Descarga de reportes operativos PDF/XLSX para ADMIN, MANAGER y AUDITOR. |

La sidebar se convierte en menú desplegable en móvil. Nombre/rol y logout quedan
visibles en el header. No hay ruta de usuarios. Reportes usa un fetch autenticado
que envía Bearer desde sessionStorage, obtiene el blob y revoca su object URL;
401 limpia la sesión y 403 conserva la sesión con feedback.

Las tablas de consulta muestran 25 filas por página y habilitan Siguiente cuando
reciben una página completa; sin consulta de total
extra, la página posterior puede estar vacía. Todas las vistas incluyen loading,
empty y error con feedback o reintento. Los 400 muestran validación genérica porque
el backend no refleja valores del request; 409 informa conflicto y refresca alertas.

## Permisos y HITL

ADMIN/MANAGER crean, editan y activan/desactivan contexto. ANALYST/AUDITOR lo
consultan. AUDITOR no ve controles de análisis ni HITL. Auditoría solo se muestra a
ADMIN/AUDITOR, y la ruta directa también limita acceso. El backend vuelve a verificar
el User de PostgreSQL; ocultar controles no sustituye autorización.

OPEN → Tomar revisión → UNDER_REVIEW asignada al actor. Claim propio repetido es
idempotente; de otra persona o CLOSED produce 409. UNDER_REVIEW → Liberar → OPEN.
ANALYST solo libera/resuelve su asignación; ADMIN/MANAGER pueden intervenir sobre
otra. La UI identifica al responsable por nombre y permite esa supervisión.

Confirmar BEC o Marcar falso positivo abre un dialog nativo con la decisión explícita.
Resolution es obligatoria, trim y 1–2000 caracteres. Confirmar decisión ejecuta resolve,
cierra la alerta y conserva responsable, verdict, resolución y fecha. El botón se
bloquea durante la petición. No hay cierre de un click ni optimistic update complejo.
CLOSED muestra el resultado humano sin controles de mutación; no hay reopen.
Resolución idéntica repetida es idempotente, otra decisión produce 409.

## Evidencia segura y accesibilidad

El email se considera texto no confiable. React escapa headers, body, señales y
resolución. El cuerpo usa pre con white-space:pre-wrap, sin dangerouslySetInnerHTML,
HTML renderizado, scripts ni links activos extraídos del body. Las contribuciones
se muestran solo para señales RULE/CONTEXT con peso; el cero semántico no se presenta
como una valoración de importancia. ERROR nunca se muestra como LOW ni score cero.
La referencia bancaria no se muestra en tablas y conserva el acceso existente del
backend, también para consulta en detalle por los roles lectores.

Labels reales, botones/links semánticos, headers de tabla, foco visible, skip link,
feedback role=status/alert y badges con texto. Dialog usa showModal, Escape, ciclo
Tab/Shift+Tab y restaura foco. Las tablas tienen una región enfocable para scroll
horizontal de teclado. Navegación y acciones esenciales funcionan a 375 px sin
comprimir columnas hasta hacerlas ilegibles. Contraste, teclado y responsive se
revisaron de forma práctica; no constituye auditoría WCAG formal.

## Tests y revisión

`npm test -- --run` ejecuta Vitest + Testing Library + jsdom; CI lo ejecuta además de
lint, formato y build. Tests usan fetch local controlado, sin MSW/browser ni proveedor
externo. Cubre sesión, 401/403, rutas protegidas, permisos, dashboard, filtros, detalle,
claim/release, veredictos, 409, render seguro, correo/análisis/retry, contexto y audit.

Chromium temporal fuera del repo valida 1440×900, 1024×768 y 375×800. Para composición
se interceptan respuestas desde Playwright; no hay mocks en producción. El recorrido
real usa otra API con PostgreSQL 18 descartable y analizador inyectado solo en su
proceso de prueba. No crea usuarios/casos ficticios en desarrollo ni llama LLM real.
La aplicación conserva el servidor Vite de desarrollo de Compose: publicar en
producción, hardening HTTP y un servidor estático dedicado siguen fuera de esta fase.
