# Chatbot RAG — Reglamento General de Alumnos (Universidad Lamar)

Chatbot con búsqueda semántica (RAG — *Retrieval-Augmented Generation*) sobre el **Reglamento
General de Alumnos de Licenciaturas y Posgrados SEP (R-0)** del Centro Universitario Guadalajara
Lamar. El sistema permite a un usuario hacer preguntas en lenguaje natural sobre el reglamento y
recibir como respuesta el artículo más relevante, obtenido mediante similitud vectorial contra una
base de datos PostgreSQL con la extensión **pgvector**, alojada en **AWS RDS**.

## 1. Descripción general

El flujo del sistema es el siguiente:

1. El reglamento (PDF) se procesa una sola vez de forma offline: se extrae su texto y se segmenta
   en artículos individuales (ver sección 6).
2. Cada artículo se convierte en un vector numérico (*embedding*) mediante un modelo de lenguaje
   preentrenado y se almacena en PostgreSQL junto con su metadata (número de artículo, capítulo,
   texto).
3. En tiempo de consulta, la pregunta del usuario se convierte también en un embedding y se compara
   contra los embeddings almacenados usando distancia coseno, para recuperar el o los artículos más
   similares semánticamente.
4. El backend arma una respuesta a partir del artículo más relevante y la regresa al frontend junto
   con sus fuentes (artículo, capítulo y puntaje de similitud).

No se utiliza ningún modelo de lenguaje generativo (LLM) de pago: la respuesta se construye
directamente a partir del contenido textual del artículo recuperado, lo que permite que el proyecto
funcione de forma completamente autónoma y sin costos de API externa.

## 2. Arquitectura

| Componente          | Tecnología                                   | Responsabilidad                                                                 |
|----------------------|-----------------------------------------------|----------------------------------------------------------------------------------|
| Base de datos vectorial | AWS RDS (PostgreSQL) + extensión `pgvector`  | Almacena los artículos del reglamento junto con su embedding y metadata; resuelve la búsqueda por similitud (distancia coseno) e índices HNSW. |
| Modelo de embeddings | `sentence-transformers` (`all-MiniLM-L6-v2`) | Convierte texto (artículos y preguntas del usuario) en vectores de 384 dimensiones. |
| Backend              | FastAPI (Python)                             | Expone el endpoint `POST /api/chat`: recibe la pregunta, calcula su embedding, consulta pgvector y arma la respuesta. |
| Frontend             | HTML + JavaScript (sin frameworks)           | Interfaz de chat que consume el backend vía `fetch` y muestra la respuesta y sus fuentes. |

Diagrama simplificado del flujo de una consulta:

```
Usuario (frontend)
   │  pregunta en lenguaje natural
   ▼
Backend FastAPI (/api/chat)
   │  1. calcula embedding de la pregunta (sentence-transformers)
   │  2. busca los artículos más similares (pgvector, distancia coseno)
   ▼
AWS RDS (PostgreSQL + pgvector) — tabla reglamento_chunks
   │  regresa artículo(s) más relevante(s) + similitud
   ▼
Backend FastAPI
   │  arma la respuesta con el artículo y sus fuentes
   ▼
Usuario (frontend) — respuesta + fuentes citadas
```

## 3. Estructura del repositorio

```
chatbot-reglamento/
├── scripts_ingestion/
│   ├── 1_extraer_chunks.py     # Extrae el texto del PDF y lo segmenta por artículo -> chunks.json
│   └── 2_cargar_embeddings.py  # Calcula el embedding de cada artículo y lo inserta en AWS RDS
├── backend/
│   └── main.py                 # API FastAPI: expone POST /api/chat (búsqueda semántica en pgvector)
├── frontend/
│   └── index.html              # Interfaz de chat en HTML/JS, consume el backend
├── reglamento.pdf               # PDF fuente del reglamento (no se sube al repositorio)
├── .gitignore
└── README.md
```

### `scripts_ingestion/`

Contiene los scripts de ingesta, que se ejecutan **una sola vez** (o cada vez que el reglamento
cambie) para poblar la base de datos:

- **`1_extraer_chunks.py`**: lee `reglamento.pdf`, extrae su texto y lo segmenta en artículos
  individuales, generando un archivo intermedio `chunks.json` para poder revisar el resultado antes
  de tocar la base de datos.
- **`2_cargar_embeddings.py`**: lee `chunks.json`, calcula el embedding de cada artículo con
  `sentence-transformers` y lo inserta en la tabla `reglamento_chunks` de AWS RDS.

### `backend/`

Contiene la API en FastAPI (`main.py`) que expone el endpoint `POST /api/chat`, usado por el
frontend para resolver las preguntas del usuario contra la base vectorial.

### `frontend/`

Contiene `index.html`, una interfaz de chat en HTML/JavaScript puro (sin frameworks ni dependencias
de Node) que se abre directamente en el navegador y consume la API del backend.

## 4. Base de datos

La base de datos (`reglamento_db`) corre en una instancia de **AWS RDS PostgreSQL** con la
extensión `pgvector` habilitada. La tabla principal es:

```sql
CREATE TABLE reglamento_chunks (
    id SERIAL PRIMARY KEY,
    capitulo VARCHAR(100),
    articulo INT,
    texto_contenido TEXT NOT NULL,
    metadata JSONB,
    embedding vector(384)
);
```

Con índices sobre `embedding` (HNSW, distancia coseno, para la búsqueda semántica), `articulo`
(búsqueda directa por número de artículo) y `metadata` (GIN).

La creación de la instancia y la ejecución de este SQL son un paso manual, previo a correr el
código de este repositorio, y no están automatizados por ningún script del proyecto.

## 5. Instalación y ejecución paso a paso

### Requisitos previos

- Python 3.9 o superior.
- Acceso a una instancia de AWS RDS (PostgreSQL) con `pgvector` habilitado y la tabla
  `reglamento_chunks` ya creada (ver sección 4).
- Endpoint, usuario y contraseña de esa instancia.
- El archivo `reglamento.pdf` colocado en la raíz del proyecto.

### Paso 1 — Crear y activar el entorno virtual

```bash
python -m venv venv

# Activar el entorno
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### Paso 2 — Instalar dependencias

```bash
pip install fastapi uvicorn psycopg2-binary sentence-transformers pymupdf numpy
```

### Paso 3 — Configurar las credenciales de AWS RDS

El Endpoint y la contraseña de la instancia de AWS RDS **no se escriben en el código**: se leen
desde variables de entorno (`ENDPOINT_AWS` y `DB_PASSWORD`), para no dejar credenciales en texto
plano en archivos versionados. `scripts_ingestion/2_cargar_embeddings.py` y `backend/main.py`
señalan esto en su bloque `# ======= CONFIGURA ESTO =======` y fallan con un mensaje claro si las
variables no están definidas.

Definir las variables antes de correr cualquiera de los dos scripts:

```bash
# Windows (PowerShell)
$env:ENDPOINT_AWS = "tu-endpoint.rds.amazonaws.com"
$env:DB_PASSWORD  = "tu-password"

# Mac/Linux
export ENDPOINT_AWS="tu-endpoint.rds.amazonaws.com"
export DB_PASSWORD="tu-password"
```

Estas variables solo viven en la sesión de terminal donde se definen; hay que volver a exportarlas
si se abre una terminal nueva. `1_extraer_chunks.py` no requiere credenciales: solo procesa el PDF
localmente.

### Paso 4 — Ejecutar la ingesta (una sola vez)

```bash
cd scripts_ingestion
python 1_extraer_chunks.py
```

Esto genera `chunks.json`. Se recomienda revisarlo antes de continuar, confirmando que el texto de
varios artículos esté completo y correctamente asociado a su capítulo.

```bash
python 2_cargar_embeddings.py
```

Esto calcula los embeddings (descarga el modelo `all-MiniLM-L6-v2` la primera vez) y los inserta en
`reglamento_chunks` en AWS RDS.

Verificación en pgAdmin/DBeaver:

```sql
SELECT COUNT(*) FROM reglamento_chunks;
SELECT articulo, capitulo, LEFT(texto_contenido, 60) FROM reglamento_chunks ORDER BY articulo LIMIT 5;
```

### Paso 5 — Levantar el backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

La API queda disponible en `http://localhost:8000`. Puede probarse directamente desde la
documentación interactiva en `http://localhost:8000/docs`.

### Paso 6 — Abrir el frontend

Con el backend corriendo, abrir `frontend/index.html` directamente en el navegador (no requiere
servidor propio).

## 6. Cómo probar el sistema

Con el backend y el frontend activos, algunos ejemplos de consulta:

| Pregunta | Respuesta esperada |
|---|---|
| `¿Qué dice el artículo 4 del reglamento?` | El texto completo del Artículo 4, junto con su capítulo (`Capítulo I - DEL ÁMBITO DE OBSERVANCIA Y VIGENCIA`) y su puntaje de similitud. Al mencionar explícitamente el número de artículo, el backend filtra directo por esa metadata antes de aplicar la búsqueda por similitud. |
| `¿Cuáles son las causas de baja de un alumno?` | El o los artículos semánticamente más cercanos al concepto de "baja de alumno", recuperados por similitud vectorial pura (sin mención explícita de un número de artículo). |

Cada respuesta incluye una sección de **fuentes**, con el número de artículo, su capítulo y el
puntaje de similitud coseno correspondiente, lo que permite verificar que la respuesta esté
respaldada por el contenido real del reglamento.

## 7. Segmentación del reglamento (chunking)

El reglamento se segmenta por **artículo**, ya que es la unidad mínima de contenido con sentido
jurídico completo dentro del documento: cada artículo expresa una regla o disposición autocontenida,
lo que lo hace la unidad ideal tanto para generar un embedding representativo como para citarlo como
fuente verificable en la respuesta.

Adicionalmente, cada artículo se etiqueta con el **capítulo** (o, en su defecto, el **título**) bajo
el cual aparece en el documento, replicando la jerarquía real del reglamento (Título → Capítulo →
Artículo). Esta metadata se guarda junto con el embedding y cumple dos propósitos:

- Permite filtrar directamente por número de artículo cuando el usuario lo menciona explícitamente
  en su pregunta (por ejemplo, "dame el artículo 4"), sin depender únicamente de la búsqueda
  semántica.
- Da contexto adicional en la respuesta (el usuario sabe no solo qué artículo aplica, sino en qué
  sección del reglamento se ubica).

La extracción del texto se hace con `pymupdf`, y la segmentación por artículo y por
capítulo/título se resuelve con expresiones regulares sobre los encabezados del documento
(`Artículo N`, `Capítulo N`, `Título N`), respetando el orden en que aparecen en el texto para
asignar a cada artículo el capítulo o título vigente en su posición dentro del documento.
