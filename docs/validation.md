# Validación de Fases 0 y 1

Validación realizada el 20 de octubre de 2026 en Linux.

## Resultados

| Comprobación | Resultado |
| --- | --- |
| Backend: `pytest` | 3 pruebas aprobadas, sin advertencias tras usar httpx2. |
| Backend: Ruff check y format check | Aprobados. |
| Frontend: ESLint | Aprobado. |
| Frontend: Prettier check | Aprobado. |
| Frontend: TypeScript y build Vite | Aprobados. |
| `docker compose config --quiet` | Código de salida 0 con `.env` configurado. |
| `docker compose up --build -d --wait --wait-timeout 180` | Imágenes construidas; los cuatro servicios healthy. |
| FastAPI `/health` | HTTP 200 y contrato esperado, consultando PostgreSQL real. |
| Vite `/health` | HTTP 200 mediante proxy al backend real. |
| PostgreSQL | `SELECT 1` devuelve 1; ninguna tabla en `public`; tablas internas de n8n en su esquema. |
| n8n `/healthz/readiness` | HTTP 200, `{"status":"ok"}` al terminar su inicialización. |
| Chromium: flujo completo | React muestra “Backend conectado ✓” tras petición real a FastAPI y PostgreSQL. |
| Chromium: error y reintento | Un 503 simulado en la red del navegador muestra no disponible; al retirar la simulación el reintento vuelve a conectar con la API real. |
| Chromium: móvil | Sin desbordamiento horizontal a 375 px. |
| Chromium: n8n | Página de creación de propietario accesible; no se creó cuenta ni workflow. |
| Secretos | `.env` y variantes locales ignorados; permisos 600; `.env.example` sin secretos. |

La comprobación del navegador usó Playwright temporalmente en `/tmp`, sin añadirlo
como dependencia del repositorio. Las pruebas unitarias del backend sustituyen la
conexión SQLAlchemy; las comprobaciones de Compose y navegador usan PostgreSQL real.

## Particularidades del entorno

- El acceso a Docker, las descargas y TestClient requirieron ejecución fuera del
  sandbox. TestClient se bloqueaba dentro del entorno restringido; fuera de él
  pasó correctamente.
- El equipo ya usaba 5432 para otro PostgreSQL. Solo el `.env` local usa
  `POSTGRES_PORT=5433`; `.env.example` conserva el valor convencional 5432.
- n8n devolvió 503 durante la primera inicialización y después quedó healthy.
  Emite avisos propios sobre defaults futuros y su runner interno de código.
  No impiden usar el editor. No se añadió un servicio de runners porque esta
  fase no ejecuta workflows ni nodos de código.

No hay autenticación de BEC Guard, modelos SQL del dominio, motor BEC, scoring,
integraciones LLM, recepción real de correos, workflows ni dashboards implementados.
