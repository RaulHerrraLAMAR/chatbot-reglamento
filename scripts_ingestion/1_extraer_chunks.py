"""
Paso 1 de la ingesta: extrae el texto del PDF del reglamento y lo segmenta
por artículo. Genera `chunks.json`, que usará el script 2 para calcular
embeddings y cargarlos a AWS RDS.

Ejecutar una sola vez (y cuantas veces sea necesario mientras se ajusta el
regex de segmentación):

    cd scripts_ingestion
    python 1_extraer_chunks.py

Revisa `chunks.json` después de correrlo: confirma que el texto de 2-3
artículos esté completo y no mezclado con el artículo siguiente. Si el PDF
tiene un formato distinto al esperado, ajusta `patron_articulo` /
`patron_capitulo` antes de continuar al script 2.
"""

import fitz  # pymupdf
import re
import json


RUTA_PDF = "../reglamento.pdf"
SALIDA_JSON = "chunks.json"

patron_articulo = re.compile(
    r'(Art[íi]culo\s+(\d+)[o°]?\.?.*?)(?=Art[íi]culo\s+\d+[o°]?\.|\Z)',
    re.DOTALL | re.IGNORECASE
)
patron_capitulo = re.compile(
    r'Cap[íi]tulo\s+([IVXLCDM]+)\s*[-—]?\s*(.*)',
    re.IGNORECASE
)
patron_titulo = re.compile(
    r'T[íi]tulo\s+([IVXLCDM]+)\s*[-—]?\s*(.*)',
    re.IGNORECASE
)


def extraer_texto(pdf_path):
    doc = fitz.open(pdf_path)
    texto = ""
    for pagina in doc:
        texto += pagina.get_text()
    return texto


def segmentar_reglamento(texto):
    lineas = texto.split("\n")

    # 1) Localizar cada encabezado de capítulo y de título con su posición
    #    (offset) dentro del texto completo. En este PDF el número de
    #    capítulo/título y su nombre quedan en líneas separadas
    #    ("Capítulo I" / "DEL ÁMBITO..."), así que el nombre se toma de la
    #    línea siguiente.
    capitulos = []  # lista de (offset, "Capítulo N - Nombre")
    titulos = []    # lista de (offset, "Título N - Nombre")
    offset = 0
    for i, linea in enumerate(lineas):
        siguiente = lineas[i + 1].strip() if i + 1 < len(lineas) else ""
        m_cap = patron_capitulo.match(linea.strip())
        if m_cap:
            capitulos.append((offset, f"Capítulo {m_cap.group(1)} - {siguiente}".strip()))
        m_tit = patron_titulo.match(linea.strip())
        if m_tit:
            titulos.append((offset, f"Título {m_tit.group(1)} - {siguiente}".strip()))
        offset += len(linea) + 1  # +1 por el "\n" que quitó split

    # 2) Recorrer los artículos en el orden en que aparecen en el documento y
    #    asignarles el capítulo vigente en su posición (el último encabezado
    #    de capítulo cuyo offset sea <= la posición del artículo). Si en ese
    #    punto del documento todavía no ha aparecido ningún capítulo (p. ej.
    #    artículos que van directo bajo un "Título" sin subdividirse en
    #    capítulos), se usa el título vigente como respaldo.
    chunks = []
    idx_cap = 0
    idx_tit = 0
    capitulo_actual = None
    titulo_actual = None
    for match in patron_articulo.finditer(texto):
        pos = match.start()
        while idx_cap < len(capitulos) and capitulos[idx_cap][0] <= pos:
            capitulo_actual = capitulos[idx_cap][1]
            idx_cap += 1
        while idx_tit < len(titulos) and titulos[idx_tit][0] <= pos:
            titulo_actual = titulos[idx_tit][1]
            idx_tit += 1

        articulo_num = int(match.group(2))
        contenido = match.group(1).strip()
        chunks.append({
            "articulo": articulo_num,
            "capitulo": capitulo_actual if capitulo_actual is not None else titulo_actual,
            "tipo": "reglamento",
            "texto": contenido
        })
    return chunks


if __name__ == "__main__":
    print(f"Leyendo {RUTA_PDF} ...")
    texto = extraer_texto(RUTA_PDF)

    print("Segmentando por artículo...")
    chunks = segmentar_reglamento(texto)

    print(f"Se encontraron {len(chunks)} artículos.")
    with open(SALIDA_JSON, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"Guardado en {SALIDA_JSON}. Revísalo antes de continuar al Paso 5 (script 2).")
