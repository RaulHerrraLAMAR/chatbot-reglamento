"""
Paso 2 de la ingesta: lee `chunks.json` (generado por 1_extraer_chunks.py),
calcula el embedding de cada artículo con sentence-transformers y lo inserta
en la tabla `reglamento_chunks` de AWS RDS.

Requiere que ya hayas corrido manualmente el SQL de creación de base de
datos / extensión pgvector / tabla / índices (paso 2 de la guía).

Antes de correrlo, define las variables de entorno ENDPOINT_AWS y DB_PASSWORD
(ver README.md).

Cómo correrlo:

    python 2_cargar_embeddings.py
"""

import json
import os

import psycopg2
from sentence_transformers import SentenceTransformer


# ======= CONFIGURA ESTO =======
# El Endpoint y la contraseña de AWS RDS NO se escriben aquí: se leen de
# variables de entorno para no dejar credenciales en texto plano en el
# código. Defínelas antes de correr este script, por ejemplo:
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
        "Defínelas antes de correr este script (ver README.md)."
    )
# ================================

ENTRADA_JSON = "chunks.json"
PORT = "5432"
USER = "postgres"
DB_NAME = "reglamento_db"


def main():
    print("Cargando modelo de embeddings (puede tardar la primera vez)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")

    print("Conectando a AWS RDS...")
    conn = psycopg2.connect(
        host=ENDPOINT_AWS, port=PORT, user=USER, password=PASSWORD, dbname=DB_NAME
    )
    cursor = conn.cursor()

    with open(ENTRADA_JSON, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    print(f"Insertando {len(chunks)} artículos con sus embeddings...")
    for chunk in chunks:
        vec = model.encode(chunk["texto"]).tolist()
        metadata = json.dumps({
            "articulo": chunk["articulo"],
            "capitulo": chunk["capitulo"],
            "tipo": chunk["tipo"]
        })
        cursor.execute(
            """
            INSERT INTO reglamento_chunks (capitulo, articulo, texto_contenido, metadata, embedding)
            VALUES (%s, %s, %s, %s, %s);
            """,
            (chunk["capitulo"], chunk["articulo"], chunk["texto"], metadata, vec)
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("¡Listo! Los artículos ya están en AWS RDS con sus embeddings.")


if __name__ == "__main__":
    main()
