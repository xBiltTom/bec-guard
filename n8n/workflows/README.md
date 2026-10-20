# Workflows de n8n

Aquí se versionarán las exportaciones JSON de workflows cuando se implemente la
orquestación. No hay workflows en las fases 0 y 1 ni se importan automáticamente.

La instancia usa PostgreSQL (esquema `n8n`) y el volumen `n8n_data` conserva su
configuración y claves de cifrado. El primer acceso pide crear su cuenta propietaria;
es la administración propia de n8n, no autenticación de BEC Guard.

Antes de versionar una exportación, elimina secretos y datos reales de correos.
Los futuros flujos llamarán a `http://backend:8000` desde la red de Compose.
La lógica BEC pertenecerá a FastAPI.
