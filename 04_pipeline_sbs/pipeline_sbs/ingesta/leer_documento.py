"""Un lector para cada formato: PDF digital o escaneado, imagen, DOCX, HTML y correo con adjunto.

El lector entrega el texto que el archivo ya trae y marca lo que necesita OCR: páginas sin capa de texto,
imágenes y adjuntos. ``aplicar_ocr`` lee lo pendiente con ``glm-ocr`` (local) o con Tesseract (S03).
Incluye los campos rotulados («RUC: …») y la normalización: fecha AAAA-MM-DD, monto a número, RUC y DNI.
"""
from __future__ import annotations

import re
import time
import unicodedata
from datetime import date
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any

import cv2
import docx
import numpy as np
import pymupdf

from ..calidad.puntuar import MESES, validar_ruc
from ..llm.cliente_llm import configuracion_llm, leer_yaml, preguntar
from ..ocr.leer import leer_con_confianza
from ..ocr.preprocesar import a_gris, corregir_inclinacion

FORMATOS = {".pdf": "pdf", ".docx": "docx", ".html": "html", ".htm": "html", ".eml": "correo",
            ".jpg": "imagen", ".jpeg": "imagen", ".png": "imagen"}
MINIMO_CARACTERES = 50  # una página con menos caracteres no tiene capa de texto útil: va a OCR
MAXIMO_TOKENS_OCR = 4096  # tope de salida del OCR por página
CAMPOS_FECHA = {"fecha", "fecha_contrato", "vigencia", "vigencia_desde", "vigencia_hasta", "periodo", "fecha_presentacion"}
CAMPOS_NUMERO = {"suma_asegurada", "prima_anual", "deducible_pct", "monto", "plazo_meses", "tea", "tcea",
                 "penalidad_mora_diaria_pct", "cuota_mensual", "total_activo", "total_pasivo", "total_patrimonio",
                 "utilidad_neta", "monto_reclamado", "plazo_dias", "n_productos"}
ROTULOS = {
    "poliza": {"numero_poliza": "Poliza:", "aseguradora": "Aseguradora:", "ruc": "RUC", "asegurado": "Asegurado",
               "dni": "DNI", "ramo": "Ramo", "suma_asegurada": "Suma asegurada", "prima_anual": "Prima anual",
               "vigencia_desde": "Vigencia desde", "vigencia_hasta": "Vigencia hasta",
               "beneficiario": "Beneficiario", "deducible_pct": "Deducible"},
    "contrato": {"numero_contrato": "N°", "ruc": "RUC", "dni_cliente": "DNI", "tcea": "TCEA"},
    "oficio": {"numero_oficio": "OFICIO N°", "fecha": "Lima,", "entidad": "Senores", "ruc": "RUC",
               "asunto": "Asunto:", "referencia": "Referencia:", "firmante": "Atentamente,"},
    "estado_financiero": {"ruc": "RUC", "periodo": "Al", "total_activo": "Total activo", "total_pasivo": "Total pasivo",
                          "total_patrimonio": "Total patrimonio", "utilidad_neta": "Utilidad neta"},
    "voucher": {"numero_operacion": "Operacion:", "fecha": "Fecha:", "hora": "Hora:", "cuenta_destino": "Cuenta:",
                "titular": "Titular:", "depositante": "Depositante:", "dni_depositante": "DNI:", "monto": "MONTO"},
    "reclamo": {"nombre": "Cliente:", "dni": "DNI"},
    "tarifario": {"ruc": "RUC", "vigencia": "Vigente desde"},
}
CON_MONEDA = ("poliza", "contrato", "estado_financiero", "voucher")


class FormatoNoSoportado(ValueError):
    """El archivo no tiene lector (por ejemplo, un ``.doc`` antiguo de Word)."""


# ------------------------------------------------------------------------------------------------ normalización
def plano(texto: Any) -> str:
    """Minúsculas, sin tildes y con un solo espacio: ``Política  N°`` queda ``politica n°``."""
    base = "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", base.lower()).strip(" .,:;")


def a_iso(valor: Any) -> str | None:
    """Convierte una fecha escrita (``24/06/2026``, ``24 de junio de 2026`` o ``2026-06-24``) a ``AAAA-MM-DD``."""
    if valor is None:
        return None
    texto = plano(valor)
    partes = None
    if encontrado := re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", texto):
        partes = (encontrado[1], encontrado[2], encontrado[3])
    elif encontrado := re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", texto):
        partes = (encontrado[3], encontrado[2], encontrado[1])
    elif (encontrado := re.search(r"(\d{1,2}) de ([a-z]+) (?:de|del) (\d{4})", texto)) and encontrado[2] in MESES:
        partes = (encontrado[3], MESES[encontrado[2]], encontrado[1])
    try:
        return date(int(partes[0]), int(partes[1]), int(partes[2])).isoformat() if partes else None
    except ValueError:
        return None


def a_numero(valor: Any) -> float | None:
    """Convierte un monto a número: ``S/ 2,643.00`` y ``2643`` dan ``2643.0``."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    encontrado = re.search(r"(\d[\d,]*(?:\.\d+)?)", str(valor))
    return float(encontrado[1].replace(",", "")) if encontrado else None


def formas_de_fecha(iso: str) -> list[str]:
    """Las formas en que una fecha ``AAAA-MM-DD`` puede aparecer escrita en un documento."""
    anio, mes, dia = iso.split("-")
    nombres = [nombre for nombre, numero in MESES.items() if numero == int(mes)]
    return ([iso, f"{dia}/{mes}/{anio}", f"{int(dia)}/{mes}/{anio}"]
            + [f"{d} de {n} de {anio}" for n in nombres for d in (dia, int(dia))])


def normalizar(campo: str, valor: Any) -> Any:
    """Deja el valor listo para usar según el campo: número, fecha ISO, RUC válido (módulo 11) o DNI de 8 cifras."""
    if valor is None or (isinstance(valor, str) and not valor.strip()):
        return None
    if campo in CAMPOS_NUMERO:
        return a_numero(valor)
    if campo in CAMPOS_FECHA:
        return a_iso(valor)
    if campo.startswith("ruc"):
        cifras = re.sub(r"\D", "", str(valor))
        return cifras if validar_ruc(cifras) else None
    if campo.startswith("dni"):
        cifras = re.sub(r"\D", "", str(valor))
        return cifras if re.fullmatch(r"\d{8}", cifras) else None
    return str(valor).strip()


# ------------------------------------------------------------------------------------------------ lectura
def _paginas_pdf(doc: dict[str, Any], datos: bytes, origen: str) -> None:
    """Agrega cada página del PDF; si no trae capa de texto, la deja pendiente de OCR."""
    with pymupdf.open(stream=datos, filetype="pdf") as pdf:
        for numero, pagina in enumerate(pdf):
            texto = pagina.get_text().strip()
            if len(texto) >= MINIMO_CARACTERES:
                doc["partes"].append(texto)
            else:
                doc["partes"].append("")
                doc["pendientes"].append({"parte": len(doc["partes"]) - 1, "clase": "pdf", "datos": datos,
                                          "pagina": numero, "origen": f"{origen} página {numero + 1}"})


def _texto_html(html: str) -> str:
    """Quita los bloques de programa (``<script>``), los estilos y las etiquetas; cada fila de tabla queda en una línea con sus celdas separadas por «|»."""
    html = re.sub(r"(?is)<(script|style|title).*?</\1>", " ", html)
    html = re.sub(r"(?i)</t[dh]>", " | ", re.sub(r"(?i)</(tr|p|div|h\d|li)>|<br\s*/?>", "\n", html))
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def leer_documento(ruta: str | Path) -> dict[str, Any]:
    """Lee un archivo con el lector de su formato.

    Returns:
        ``{"archivo", "formato", "partes", "pendientes", "cabecera"}``: ``partes`` es el texto por página o por pieza
        (vacío donde falta OCR); ``pendientes`` lista lo que necesita OCR; ``cabecera`` trae De y Asunto si es un correo.

    Raises:
        FormatoNoSoportado: si la extensión no tiene lector (por ejemplo, ``.doc``).
    """
    ruta = Path(ruta)
    formato = FORMATOS.get(ruta.suffix.lower())
    if formato is None:
        raise FormatoNoSoportado(f"{ruta.name}: formato no soportado ({ruta.suffix}); se convierte a PDF o DOCX antes de procesarlo.")
    doc: dict[str, Any] = {"archivo": ruta.name, "formato": formato, "partes": [], "pendientes": [], "cabecera": None}
    if formato == "pdf":
        _paginas_pdf(doc, ruta.read_bytes(), "PDF")
    elif formato == "docx":
        documento = docx.Document(str(ruta))
        lineas = [p.text for p in documento.paragraphs if p.text.strip()]
        lineas += [" | ".join(c.text.strip() for c in fila.cells) for tabla in documento.tables for fila in tabla.rows]
        doc["partes"].append("\n".join(lineas))
    elif formato == "html":
        doc["partes"].append(_texto_html(ruta.read_text(encoding="utf-8", errors="replace")))
    elif formato == "correo":
        with ruta.open("rb") as archivo:
            mensaje = BytesParser(policy=policy.default).parse(archivo)
        doc["cabecera"] = {"De": str(mensaje["From"]), "Asunto": str(mensaje["Subject"])}
        doc["partes"].append(mensaje.get_body(preferencelist=("plain",)).get_content().strip())
        for adjunto in mensaje.iter_attachments():
            if adjunto.get_content_type() == "application/pdf":
                _paginas_pdf(doc, adjunto.get_content(), "adjunto PDF")
            else:
                doc["partes"].append("")
                doc["pendientes"].append({"parte": len(doc["partes"]) - 1, "clase": "imagen",
                                          "datos": adjunto.get_content(), "pagina": 0, "origen": "adjunto imagen"})
    else:
        doc["partes"].append("")
        doc["pendientes"].append({"parte": 0, "clase": "imagen", "datos": ruta.read_bytes(), "pagina": 0, "origen": "imagen"})
    return doc


def texto_de(doc: dict[str, Any]) -> str:
    """Todo el texto disponible del documento; en un correo, con el remitente y el asunto al inicio."""
    cuerpo = "\n".join(parte for parte in doc["partes"] if parte)
    cabecera = doc.get("cabecera")
    return f"De: {cabecera['De']}\nAsunto: {cabecera['Asunto']}\n{cuerpo}" if cabecera else cuerpo


# ------------------------------------------------------------------------------------------------ OCR
def _imagen_de(pendiente: dict[str, Any], dpi: int) -> bytes:
    """La página del PDF dibujada como PNG, o la imagen tal como llegó."""
    if pendiente["clase"] == "imagen":
        return pendiente["datos"]
    with pymupdf.open(stream=pendiente["datos"], filetype="pdf") as pdf:
        return pdf[pendiente["pagina"]].get_pixmap(dpi=dpi).tobytes("png")


def aplicar_ocr(doc: dict[str, Any], motor: str = "glm", num_ctx: int | None = None, dpi: int | None = None,
                cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lee con OCR lo pendiente del documento y devuelve una copia con el texto completo.

    Args:
        doc: salida de ``leer_documento``.
        motor: ``glm`` (``glm-ocr`` en Ollama, local) o ``tesseract`` (S03: escala de grises y enderezado).
        num_ctx: contexto de ``glm-ocr``; por defecto ``llm.num_ctx_ocr`` (8192). Con 4096 la imagen llena el contexto.
        dpi: resolución de la página; por defecto ``ocr.dpi_llm`` (200) con ``glm`` y ``ocr.dpi`` (300) con ``tesseract``.
        cfg: sección ``llm`` de la configuración.

    Returns:
        Copia de ``doc`` con las partes leídas y ``ocr``: una fila por parte (origen, caracteres, segundos y fin).
    """
    cfg = cfg or configuracion_llm()
    ocr = leer_yaml()["ocr"]
    dpi = dpi or (ocr["dpi_llm"] if motor == "glm" else ocr["dpi"])
    nuevo = {**doc, "partes": list(doc["partes"]), "ocr": []}
    for pendiente in doc["pendientes"]:
        inicio = time.perf_counter()
        if motor == "glm":
            respuesta = preguntar(cfg["modelo_ocr"], "Text Recognition:", imagenes=[_imagen_de(pendiente, dpi)],
                                  num_ctx=num_ctx or cfg["num_ctx_ocr"], num_predict=MAXIMO_TOKENS_OCR, cfg=cfg)
            texto, fin = respuesta.texto.strip(), respuesta.fin
        else:
            imagen = cv2.imdecode(np.frombuffer(_imagen_de(pendiente, dpi), np.uint8), cv2.IMREAD_COLOR)
            recta, _ = corregir_inclinacion(a_gris(imagen))
            texto, fin = leer_con_confianza(recta, psm=6)["texto"].strip(), "stop"
        nuevo["partes"][pendiente["parte"]] = texto
        nuevo["ocr"].append({"origen": pendiente["origen"], "motor": motor, "caracteres": len(texto),
                             "segundos": round(time.perf_counter() - inicio, 2), "fin": fin})
    return nuevo


# ------------------------------------------------------------------------------------------------ campos rotulados
def _valor_rotulado(lineas: list[str], rotulo: str) -> str | None:
    """Lo que sigue al rótulo en su línea o, si la línea termina en el rótulo, la línea siguiente."""
    for i, linea in enumerate(lineas):
        if rotulo == "Total pasivo" and linea.lower().startswith("total pasivo y"):
            continue
        if re.match(rf"{re.escape(rotulo)}(?=$|[\s:])", linea, flags=re.I) or (len(rotulo) > 3 and f" {rotulo} " in f" {linea} "):
            resto = linea[linea.find(rotulo) + len(rotulo):] if rotulo in linea else linea[len(rotulo):]
            resto = resto.strip(" :")
            if not resto and i + 1 < len(lineas):
                resto = lineas[i + 1]
            resto = re.split(r"\s{2,}| \| |, (?=[a-z])|\. (?=[A-Z])", resto)[0].strip()
            if rotulo.startswith(("RUC", "DNI")) and resto:
                resto = resto.split()[0].strip(",.;)")
            return resto or None
    return None


def campos_rotulados(tipo: str, doc: dict[str, Any]) -> dict[str, Any]:
    """Toma los campos que el documento trae con su rótulo («RUC: …», «Suma asegurada» y la línea siguiente) y los normaliza.

    También usa las cabeceras del correo (remitente y asunto) y fija la moneda PEN si hay montos con «S/».
    """
    texto = texto_de(doc)
    lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
    crudo = {campo: _valor_rotulado(lineas, rotulo) for campo, rotulo in ROTULOS.get(tipo, {}).items()}
    if cabecera := doc.get("cabecera"):
        if encontrado := re.match(r"\s*(.*?)\s*<([^>]+)>", cabecera["De"]):
            crudo["nombre"] = crudo.get("nombre") or encontrado[1]
            crudo["correo"] = encontrado[2]
        crudo["motivo"] = cabecera["Asunto"].split(" - ", 1)[-1] if " - " in cabecera["Asunto"] else None
    campos = {campo: normalizar(campo, valor) for campo, valor in crudo.items()}
    if tipo in CON_MONEDA:
        campos["moneda"] = "PEN" if re.search(r"S/\s*\d", texto) else None
    if tipo == "estado_financiero":
        unidad = re.search(r"\(en (soles|miles de soles|millones de soles)\)", texto)
        campos["unidad"] = unidad[1] if unidad else None
    return campos
