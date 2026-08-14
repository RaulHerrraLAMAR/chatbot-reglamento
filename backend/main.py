"""
Backend FastAPI del chatbot. Expone POST /api/chat: recibe un mensaje,
calcula su embedding, busca los artículos más similares en
`reglamento_chunks` (AWS RDS + pgvector) y arma una respuesta con el
artículo más relevante y sus fuentes.

Antes de correrlo, define las variables de entorno ENDPOINT_AWS y DB_PASSWORD
(ver README.md).

Cómo correrlo:

    cd backend
    uvicorn main:app --reload --port 8000

Pruébalo en http://localhost:8000/docs (Swagger UI) antes de conectar el
frontend.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
import re
from sentence_transformers import SentenceTransformer


# ======= CONFIGURA ESTO =======
# El Endpoint y la contraseña de AWS RDS NO se escriben aquí: se leen de
# variables de entorno para no dejar credenciales en texto plano en el
# código. Defínelas antes de levantar el backend, por ejemplo:
#
#   Windows (PowerShell):
#     $env:ENDPOINT_AWS = "tu-endpoint.rds.amazonaws.com"
#     $env:DB_PASSWORD  = "tu-password"
#
#   Mac/Linux:
#     export ENDPOINT_AWS="tu-endpoint.rds.amazonaws.com"
#     export DB_PASSWORD="tu-password"
ENDPOINT_AWS = os.environ.get("ENDPOINT_AWS")
PASSWORD = os.environ.get("DB_PASSWORD")

if not ENDPOINT_AWS or not PASSWORD:
    raise RuntimeError(
        "Faltan las variables de entorno ENDPOINT_AWS y/o DB_PASSWORD. "
        "Defínelas antes de levantar el backend (ver README.md)."
    )


PORT = "5432"
USER = "postgres"
DB_NAME = "reglamento_db"

app = FastAPI()

# Permite que el frontend (abierto como archivo local) le hable a esta API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Cargando modelo de embeddings...")
model = SentenceTransformer("all-MiniLM-L6-v2")


class Pregunta(BaseModel):
    mensaje: str


def obtener_conexion():
    return psycopg2.connect(
        host=ENDPOINT_AWS, port=PORT, user=USER, password=PASSWORD, dbname=DB_NAME
    )


@app.get("/")
def salud():
    return {"status": "ok"}


@app.post("/api/chat")
def chat(pregunta: Pregunta):
    conn = obtener_conexion()
    cursor = conn.cursor()
    vec = model.encode(pregunta.mensaje).tolist()

    match = re.search(r"art[íi]culo\s+(\d+)", pregunta.mensaje, re.IGNORECASE)

    if match:
        cursor.execute(
            """
            SELECT texto_contenido, articulo, capitulo,
                   1 - (embedding <=> %s::vector) AS similitud
            FROM reglamento_chunks WHERE articulo = %s
            ORDER BY embedding <=> %s::vector LIMIT 3;
            """,
            (vec, int(match.group(1)), vec),
        )
    else:
        cursor.execute(
            """
            SELECT texto_contenido, articulo, capitulo,
                   1 - (embedding <=> %s::vector) AS similitud
            FROM reglamento_chunks
            ORDER BY embedding <=> %s::vector LIMIT 3;
            """,
            (vec, vec),
        )

    resultados = cursor.fetchall()
    cursor.close()
    conn.close()

    if not resultados:
        return {"respuesta": "No encontré información relacionada en el reglamento.", "fuentes": []}

    respuesta = (
        f"Según el Artículo {resultados[0][1]} ({resultados[0][2]}):\n\n{resultados[0][0]}"
    )
    fuentes = [{"articulo": r[1], "capitulo": r[2], "similitud": round(r[3], 3)} for r in resultados]

    return {"respuesta": respuesta, "fuentes": fuentes}
