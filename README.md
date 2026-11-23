# ALVEA — Estudio de Arquitectura e Inteligencia de Procesos

> *"De la narrativa operativa a la arquitectura ejecutiva."*

**ALVEA** es una aplicación web con backend en **Python**, teoría de grafos (**NetworkX**), generación ejecutiva de documentos (**ReportLab**) y un motor híbrido **Local / Multi-LLM** que transforma descripciones en lenguaje natural de procesos de negocio en **diagramas de carriles (*Swimlanes*) en Mermaid.js**, métricas estructurales en vivo y reportes ejecutivos descargables.

---

## Características Principales

### 1. Motor Híbrido: 100 % Local Sin API + Modelos Gratuitos 2026 Multi-Compañía
* **Motor Nativo Python BPA (`native_python`, Offline / Sin API):** Parser NLP determinista en español e inglés que segmenta cláusulas reales, extrae actores/carriles con resolución anafórica, agrupa compuertas de decisión (`Si... / De lo contrario...`), detecta bucles de retrabajo y compila sintaxis Mermaid válida al instante.
* **LLM 100 % Local sin API en la nube:**
  * **Ollama Local** (`http://127.0.0.1:11434`) con autodescubrimiento de modelos (`/api/tags`) y catálogo actualizado (`qwen3.8:27b`, `qwen3-coder:30b`, `gemma4:12b`, `gemma4:e4b`, `llama3.3:70b`, `llama3.1:8b`, `llama3.2:3b`, `deepseek-r1:8b`).
  * **LM Studio / OpenAI-Compatible Local** (`http://127.0.0.1:1234/v1`) con autodescubrimiento (`/v1/models`).
* **Proveedores Cloud con Capa Gratuita (2026):**
  * **Google Gemini (AI Studio):** `gemini-3.8-flash`, `gemini-3.5-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash`.
  * **Groq Cloud (LPU):** `llama-3.3-70b-versatile`, `qwen/qwen3.8-27b`, `openai/gpt-oss-120b`, `llama-3.1-8b-instant`.
  * **OpenRouter (`:free`):** `openrouter/free` (auto-router), `google/gemma-4-31b-it:free`, `google/gemma-4-26b-a4b-it:free`, `qwen/qwen3.8-27b:free`, `nvidia/nemotron-3.5-lightning:free`, `nvidia/nemotron-3-ultra-550b-a55b:free`.
  * **Cerebras Inference:** `qwen-3.8-27b`, `gpt-oss-120b`.
  * **GitHub Models:** `openai/gpt-4.1-mini`, `meta/llama-3.3-70b-instruct`, `deepseek/deepseek-r1`, `mistral-ai/mistral-small-2503`.
* **Otros Proveedores (BYOK):** Mistral AI, OpenAI, Anthropic Claude y endpoints OpenAI-Compatible personalizados.
* **Auto-Reparación en 5 Niveles:** Decodificación JSON estructurada, degradación automática de modo, limpieza de etiquetas `<think>`, auto-reparación LLM y fallback Mermaid-a-`ProcessGraph`.

### 2. Analítica de Procesos con NetworkX
Cada diagrama —generado por el motor local, por un LLM o editado manualmente— se convierte en un grafo dirigido (`nx.DiGraph`) para calcular en tiempo real:
* **Detección de ciclos de retrabajo** (`nx.simple_cycles`) y aristas de retorno.
* **Camino crítico ponderado** sobre DAG condensado (`nx.dag_longest_path`) con resaltado visual opcional.
* **Cuellos de botella** por centralidad de intermediación (`nx.betweenness_centrality`), presión de *handoffs* y carácter manual.
* **Complejidad ciclomática de McCabe**, ratio de automatización, tasa de traspasos entre carriles y calificación operativa (`A+` a `C`).
* **Auditoría estructural:** nodos huérfanos, inalcanzables, callejones sin salida y decisiones incompletas.

### 3. Estudio Visual Moderno y Exportación Ejecutiva
* Diseño editorial con tema **Sistema / Claro / Oscuro** (`color-scheme: light dark` y `light-dark()`), prevención de FOUC y diálogos top-layer accesibles.
* Orientación dinámica **Horizontal (`graph LR`)** y **Vertical (`graph TD`)**, *Pan & Zoom*, historial **Deshacer / Rehacer** (30 versiones) y atajos de teclado (`Ctrl+Enter`, `Ctrl+S`, `Ctrl+Z`, `?`).
* Exportación a **PDF Ejecutivo multipágina (ReportLab)**, **PNG HD (3x sin *tainted canvas*)**, **SVG vectorial**, **YAML / JSON** (con importación YAML validada por Pydantic) y copia directa de código Mermaid.

---

## Arquitectura del Proyecto

```text
.
├── run_alvea.py                 # Punto de entrada rápido
├── pyproject.toml               # Metadatos y empaquetado Python
├── requirements.txt             # Dependencias mínimas
├── alvea/
│   ├── config.py                # Configuración y límites de seguridad
│   ├── models.py                # Contratos tipados Pydantic v2
│   ├── security/                # Protección SSRF, Path Traversal y redacción de secretos
│   ├── engine/                  # Parser NLP BPA, compilador/validador Mermaid, NetworkX y reportes
│   ├── ai/                      # Catálogo 2026, prompts, cliente httpx y auto-reparación
│   ├── exporters/               # Exportadores PDF (ReportLab), YAML y JSON
│   └── server/                  # Servidor HTTP multihilo endurecido
├── static/                      # Frontend aislado (HTML, CSS, JS, visor standalone y Mermaid local)
├── examples/                    # Diagramas de referencia (.mmd / .md)
└── tests/                       # Suite automatizada de pruebas y auditoría de seguridad
```

---

## Instalación y Uso

### Requisitos
* **Python 3.11+**

### Arranque rápido
```bash
# 1. Crear entorno virtual (recomendado)
python -m venv .venv
source .venv/bin/activate        # En Windows: .venv\Scripts\activate

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Iniciar ALVEA (escucha en 127.0.0.1:8000 por defecto)
python run_alvea.py
```

Abre en tu navegador **`http://127.0.0.1:8000`**.

Opciones de línea de comandos:
```bash
python run_alvea.py --host 127.0.0.1 --port 8080
```

### Ejecutar la suite de pruebas
```bash
python -m unittest discover -s tests -v
```

---

## Seguridad y Privacidad por Diseño

* **Cero persistencia de API Keys en servidor:** Las claves se reciben en cabeceras HTTP (`X-API-Key`), se protegen con `pydantic.SecretStr`, se redactan automáticamente en logs y nunca se envían en query strings (`?key=...`) ni se escriben en disco.
* **Protección Anti-SSRF:** Lista blanca estricta de hosts cloud (HTTPS puerto 443), validación loopback-only para Ollama/LM Studio, resolución DNS previa con bloqueo de IPs privadas/IMDS (`169.254.169.254`), `follow_redirects=False` y validación regex de nombres de modelo.
* **Prevención XSS y CSP Estricta:** Mermaid configurado con `securityLevel: "strict"` y `htmlLabels: false`; eliminación de directivas `click`/`init` y HTML peligroso; construcción del DOM libre de `innerHTML` no sanitizado; cabecera `Content-Security-Policy` con `script-src 'self'`.
* **Confinamiento de Archivos Estáticos:** El servidor expone únicamente el subdirectorio `static/` con resolución canónica (`Path.resolve().is_relative_to()`) y lista blanca de extensiones.
* **Modo 100 % Offline:** Funciona completamente sin conexión usando el Motor Nativo Python BPA o Ollama local junto con la copia empaquetada de Mermaid.js.

---

## Licencia

Distribuido bajo licencia **MIT**. Consulta el archivo [LICENSE](LICENSE) para más detalles.
