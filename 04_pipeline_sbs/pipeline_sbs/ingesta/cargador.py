"""Cargador de lotes: abre cada archivo según su contenido, tipifica los fallos y calcula estadísticas.

Un archivo defectuoso nunca detiene el lote: se captura por archivo, se tipifica el motivo, se copia
a cuarentena y se sigue. El hash SHA-256 del contenido evita reprocesar duplicados.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import statistics
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
import pymupdf

from pipeline_sbs.config.configuracion import cargar_configuracion
from pipeline_sbs.ingesta.errores import (
    ErrorArchivoVacio,
    ErrorExtensionFalsa,
    ErrorDocxCorrupto,
    ErrorFormatoNoSoportado,
    ErrorIngesta,
    ErrorPdfCifrado,
    ErrorPdfDanado,
    traducir_excepcion,
)
from pipeline_sbs.ingesta.extractores import extraer_texto
from pipeline_sbs.preprocesamiento.normalizacion import normalizar_texto

registro = logging.getLogger(__name__)

EXTENSIONES_POR_FORMATO: dict[str, tuple[str, ...]] = {
    "pdf": (".pdf",),
    "png": (".png",),
    "jpg": (".jpg", ".jpeg"),
    "tif": (".tif", ".tiff"),
    "docx": (".docx",),
    "eml": (".eml",),
    "html": (".html", ".htm"),
}
TIPO_POR_EXTENSION: dict[str, str] = {
    ".pdf": "pdf", ".png": "imagen", ".jpg": "imagen", ".jpeg": "imagen", ".tif": "imagen", ".tiff": "imagen",
    ".docx": "word", ".eml": "correo", ".html": "html", ".htm": "html",
}
FORMATOS_IMAGEN = ("png", "jpg", "tif")
ESPERAS_REINTENTO = (1, 2, 4)      # segundos de espera ante un archivo bloqueado (antivirus o sincronizador de archivos)


# ---------------------------------------------------------------- funciones de ingesta (E4)

def calcular_sha256(ruta: str | Path) -> str:
    """Calcula la huella SHA-256 del contenido de un archivo, leyéndolo por bloques.

    Args:
        ruta: archivo a resumir.

    Returns:
        Huella en hexadecimal (64 caracteres).
    """
    resumen = hashlib.sha256()
    with Path(ruta).open("rb") as archivo:
        for bloque in iter(lambda: archivo.read(1024 * 1024), b""):
            resumen.update(bloque)
    return resumen.hexdigest()


def detectar_formato(ruta: str | Path) -> str:
    """Detecta el formato por la firma del contenido, no por la extensión.

    Args:
        ruta: archivo a revisar.

    Returns:
        "vacio", "pdf", "png", "jpg", "tif", "docx" (firma ZIP con extensión .docx), "zip", "html",
        "eml" o "desconocido".
    """
    ruta = Path(ruta)
    if ruta.stat().st_size == 0:
        return "vacio"
    with ruta.open("rb") as archivo:
        cabecera = archivo.read(2048)
    if b"%PDF-" in cabecera[:1024]:
        return "pdf"
    if cabecera.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if cabecera.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if cabecera.startswith((b"II*\x00", b"MM\x00*")):
        return "tif"
    if cabecera.startswith(b"PK\x03\x04"):
        return "docx" if ruta.suffix.lower() == ".docx" else "zip"
    texto = cabecera.decode("utf-8", errors="ignore").lstrip("﻿ \t\r\n").lower()
    if texto.startswith("<!doctype html") or "<html" in texto[:512]:
        return "html"
    cabeceras = re.findall(r"^(from|to|subject|date|mime-version|content-type|message-id):", texto, re.MULTILINE)
    if re.match(r"[a-z][\w-]*:", texto) and len(set(cabeceras)) >= 2:
        return "eml"
    return "desconocido"


def validar_formato_y_extension(ruta: str | Path, formato: str) -> None:
    """Rechaza con un error tipificado los archivos vacíos, de formato desconocido o con extensión falsa.

    Args:
        ruta: archivo revisado.
        formato: resultado de ``detectar_formato``.

    Raises:
        ErrorArchivoVacio: si el archivo tiene 0 bytes.
        ErrorFormatoNoSoportado: si el contenido no es ninguno de los formatos del pipeline.
        ErrorExtensionFalsa: si la extensión no corresponde a la firma del contenido.
    """
    ruta = Path(ruta)
    if formato == "vacio":
        raise ErrorArchivoVacio("el archivo tiene 0 bytes")
    if formato not in EXTENSIONES_POR_FORMATO:
        raise ErrorFormatoNoSoportado(f"formato '{formato}' no soportado")
    if ruta.suffix.lower() not in EXTENSIONES_POR_FORMATO[formato]:
        raise ErrorExtensionFalsa(f"la extensión '{ruta.suffix.lower()}' no corresponde al contenido ({formato})")


def verificar_apertura(ruta: str | Path, formato: str) -> None:
    """Comprueba que el archivo se puede abrir y lanza el error tipificado que corresponde.

    PyMuPDF repara en silencio un PDF truncado y devuelve texto parcial; aquí eso cuenta como dañado.

    Args:
        ruta: archivo revisado.
        formato: resultado de ``detectar_formato``.

    Raises:
        ErrorPdfCifrado: si el PDF pide contraseña.
        ErrorPdfDanado: si el PDF no se abre o solo se abre tras una reparación.
        ErrorDocxCorrupto: si el .docx no es un ZIP válido.
    """
    ruta = Path(ruta)
    if formato == "pdf":
        try:
            doc = pymupdf.open(str(ruta))
        except (pymupdf.FileDataError, pymupdf.EmptyFileError) as error:
            raise ErrorPdfDanado(f"{type(error).__name__}: no se pudo abrir el PDF") from error
        with doc:
            if doc.needs_pass:
                raise ErrorPdfCifrado("el PDF pide contraseña")
            if doc.is_repaired:
                raise ErrorPdfDanado("el PDF estaba dañado y solo se abrió tras una reparación automática")
    elif formato == "docx":
        if not zipfile.is_zipfile(ruta):
            raise ErrorDocxCorrupto("el archivo no es un ZIP válido")


def enviar_a_cuarentena(ruta: str | Path, cuarentena: str | Path, motivo: str, detalle: str = "") -> Path:
    """Copia (no mueve) un archivo defectuoso a la carpeta de cuarentena y deja junto a él su motivo.

    Es idempotente: repetir la llamada reemplaza el archivo (``Path.replace``) aunque el destino ya exista.

    Args:
        ruta: archivo defectuoso.
        cuarentena: carpeta de cuarentena (se crea si no existe).
        motivo: motivo tipificado (por ejemplo "pdf_cifrado").
        detalle: texto breve con la causa.

    Returns:
        Ruta de la copia en cuarentena.
    """
    ruta, cuarentena = Path(ruta), Path(cuarentena)
    cuarentena.mkdir(parents=True, exist_ok=True)
    destino = cuarentena / ruta.name
    temporal = destino.with_name(destino.name + ".tmp")
    shutil.copy2(ruta, temporal)
    temporal.replace(destino)
    nota = {"archivo": ruta.name, "motivo": motivo, "detalle": detalle[:300]}
    nota_tmp = destino.with_name(destino.name + ".motivo.json.tmp")
    nota_tmp.write_text(json.dumps(nota, ensure_ascii=False, indent=2), encoding="utf-8")
    nota_tmp.replace(destino.with_name(destino.name + ".motivo.json"))
    return destino


# ---------------------------------------------------------------- resultado y cargador

@dataclass
class ResultadoCarga:
    """Registro de un archivo procesado.

    Attributes:
        archivo: nombre del archivo.
        tipo: tipo recibido, según la extensión: pdf, imagen, word, correo, html u otro.
        formato: formato detectado por la firma del contenido.
        estado: "ok", "fallo" o "duplicado".
        motivo: motivo tipificado del fallo, "duplicado" o cadena vacía.
        detalle: causa en texto libre (sin rutas).
        paginas: número de páginas (0 si no se pudo leer).
        caracteres: caracteres del texto normalizado.
        segundos: tiempo de proceso medido con ``time.perf_counter``.
        requiere_ocr: True si el archivo está ok pero no trae texto suficiente.
        sha256: huella del contenido.
        duplicado_de: archivo original, si el estado es "duplicado".
        texto: texto normalizado (no se incluye en las tablas).
    """

    archivo: str
    tipo: str
    formato: str
    estado: str
    motivo: str = ""
    detalle: str = ""
    paginas: int = 0
    caracteres: int = 0
    segundos: float = 0.0
    requiere_ocr: bool = False
    sha256: str = ""
    duplicado_de: str = ""
    texto: str = field(default="", repr=False)

    def como_dict(self) -> dict[str, Any]:
        """Devuelve el registro sin el texto, listo para una tabla o un JSON."""
        datos = asdict(self)
        datos.pop("texto")
        return datos


class CargadorDocumentos:
    """Carga un lote de archivos mixtos sin que un archivo defectuoso detenga el proceso.

    Args:
        carpeta: carpeta con los archivos recibidos (sin subcarpetas).
        cuarentena: carpeta donde se copian los archivos que fallan.
        umbral_ocr: caracteres por página por debajo de los cuales un archivo ok requiere OCR.
        esperas: segundos de espera entre reintentos ante un archivo bloqueado (solo ``PermissionError``).
    """

    def __init__(self, carpeta: str | Path, cuarentena: str | Path, umbral_ocr: int = 20,
                 esperas: tuple[float, ...] = ESPERAS_REINTENTO) -> None:
        self.carpeta = Path(carpeta)
        self.cuarentena = Path(cuarentena)
        self.umbral_ocr = umbral_ocr
        self.esperas = esperas
        self._vistos: dict[str, str] = {}

    @classmethod
    def desde_configuracion(cls, carpeta: str | Path, ruta_configuracion: str | Path | None = None,
                            **cambios: Any) -> "CargadorDocumentos":
        """Crea el cargador con los valores de ``config/pipeline.yaml`` (sección ``ingesta``).

        Args:
            carpeta: carpeta del lote.
            ruta_configuracion: YAML propio; por defecto el del paquete.
            **cambios: valores que reemplazan a los de la configuración (por ejemplo ``cuarentena``).

        Returns:
            CargadorDocumentos configurado.
        """
        ingesta = cargar_configuracion(ruta_configuracion)["ingesta"]
        parametros: dict[str, Any] = {
            "cuarentena": ingesta.get("carpeta_cuarentena", "cuarentena"),
            "umbral_ocr": ingesta.get("umbral_ocr_caracteres_por_pagina", 20),
        }
        parametros.update(cambios)
        return cls(carpeta, **parametros)

    def _con_reintentos(self, funcion, *argumentos):
        """Ejecuta ``funcion``; reintenta solo ante ``PermissionError`` (archivo bloqueado), con espera creciente."""
        for espera in self.esperas:
            try:
                return funcion(*argumentos)
            except PermissionError:
                registro.warning("archivo_bloqueado", extra={"archivo": Path(argumentos[0]).name, "espera": espera})
                time.sleep(espera)
        return funcion(*argumentos)

    def cargar_uno(self, ruta: str | Path) -> ResultadoCarga:
        """Procesa un archivo y devuelve su registro; nunca lanza excepciones por el contenido del archivo.

        Pasos: huella SHA-256, formato por firma, validación contra la extensión, duplicado por huella,
        extracción, normalización y decisión de OCR. Si algo falla, el archivo se copia a cuarentena.

        Args:
            ruta: archivo a procesar.

        Returns:
            ResultadoCarga con estado "ok", "fallo" o "duplicado".
        """
        ruta = Path(ruta)
        inicio = time.perf_counter()
        tipo = TIPO_POR_EXTENSION.get(ruta.suffix.lower(), "otro")
        sha, formato = "", "desconocido"
        try:
            sha = self._con_reintentos(calcular_sha256, ruta)
            formato = self._con_reintentos(detectar_formato, ruta)
            validar_formato_y_extension(ruta, formato)
            self._con_reintentos(verificar_apertura, ruta, formato)
            original = self._vistos.get(sha)
            if original is not None and original != ruta.name:
                resultado = ResultadoCarga(archivo=ruta.name, tipo=tipo, formato=formato, estado="duplicado",
                                           motivo="duplicado", detalle=f"mismo contenido que {original}",
                                           sha256=sha, duplicado_de=original)
            else:
                extraccion = self._con_reintentos(extraer_texto, ruta, formato)
                texto = normalizar_texto(extraccion.texto)
                por_pagina = len(texto) / max(extraccion.paginas, 1)
                resultado = ResultadoCarga(
                    archivo=ruta.name, tipo=tipo, formato=formato, estado="ok", paginas=extraccion.paginas,
                    caracteres=len(texto),
                    requiere_ocr=(formato in FORMATOS_IMAGEN or (formato == "pdf" and por_pagina < self.umbral_ocr)),
                    sha256=sha, texto=texto,
                )
                self._vistos[sha] = ruta.name
        except Exception as error:  # noqa: BLE001 - un archivo malo no debe detener el lote
            tipificado = error if isinstance(error, ErrorIngesta) else traducir_excepcion(error)
            detalle = (tipificado.detalle or str(tipificado)).replace(str(ruta), ruta.name)
            resultado = ResultadoCarga(archivo=ruta.name, tipo=tipo, formato=formato, estado="fallo",
                                       motivo=tipificado.motivo, detalle=detalle, sha256=sha)
            try:
                enviar_a_cuarentena(ruta, self.cuarentena, tipificado.motivo, detalle)
            except OSError as error_copia:
                registro.error("cuarentena_fallida", extra={"archivo": ruta.name, "detalle": str(error_copia)})
            if tipificado.motivo == "error_inesperado":
                registro.exception("error_inesperado", extra={"archivo": ruta.name})
        resultado.segundos = time.perf_counter() - inicio
        registro.log(
            logging.INFO if resultado.estado == "ok" else logging.WARNING, "archivo_procesado",
            extra={"archivo": resultado.archivo, "estado": resultado.estado, "motivo": resultado.motivo,
                   "formato": resultado.formato, "segundos": round(resultado.segundos, 6)},
        )
        return resultado

    def cargar_lote(self) -> list[ResultadoCarga]:
        """Procesa todos los archivos de la carpeta, uno por uno y en orden alfabético.

        El lote es secuencial a propósito (PyMuPDF no admite hilos) y empieza sin memoria de huellas,
        así que repetirlo sobre la misma carpeta produce el mismo resultado.

        Returns:
            Un ResultadoCarga por archivo.

        Raises:
            NotADirectoryError: si la carpeta no existe.
        """
        if not self.carpeta.is_dir():
            raise NotADirectoryError(f"No existe la carpeta: {self.carpeta}")
        self._vistos = {}
        archivos = sorted(p for p in self.carpeta.iterdir() if p.is_file() and not p.name.startswith("."))
        return [self.cargar_uno(p) for p in archivos]


# ---------------------------------------------------------------- estadísticas

def tabla_resultados(resultados: list[ResultadoCarga]) -> pd.DataFrame:
    """Tabla con un registro por archivo (sin el texto), en el orden recibido.

    Args:
        resultados: salida de ``cargar_lote``.

    Returns:
        DataFrame con las columnas de ``ResultadoCarga``.
    """
    return pd.DataFrame([r.como_dict() for r in resultados])


def estadisticas(resultados: list[ResultadoCarga]) -> pd.DataFrame:
    """Resume el lote por tipo de archivo, con una fila final ``TOTAL``.

    Columnas: n, ok, fallo, duplicado, pct_ok, pct_fallo, pct_duplicado, paginas, caracteres,
    segundos_total, segundos_mediana, requiere_ocr y pct_requiere_ocr. Los porcentajes de estado
    se calculan sobre ``n``; ``pct_requiere_ocr`` se calcula **solo sobre los archivos ok**
    (un fallo o un duplicado no son candidatos a OCR).

    Args:
        resultados: salida de ``cargar_lote``.

    Returns:
        DataFrame indexado por tipo.
    """
    columnas = ["n", "ok", "fallo", "duplicado", "pct_ok", "pct_fallo", "pct_duplicado", "paginas", "caracteres",
                "segundos_total", "segundos_mediana", "requiere_ocr", "pct_requiere_ocr"]
    if not resultados:
        return pd.DataFrame(columns=columnas)
    tabla = tabla_resultados(resultados)

    def resumir(grupo: pd.DataFrame) -> dict[str, Any]:
        n = len(grupo)
        ok = int((grupo["estado"] == "ok").sum())
        fallo = int((grupo["estado"] == "fallo").sum())
        duplicado = int((grupo["estado"] == "duplicado").sum())
        con_ocr = int(((grupo["estado"] == "ok") & grupo["requiere_ocr"]).sum())
        return {
            "n": n, "ok": ok, "fallo": fallo, "duplicado": duplicado,
            "pct_ok": round(100 * ok / n, 1), "pct_fallo": round(100 * fallo / n, 1),
            "pct_duplicado": round(100 * duplicado / n, 1),
            "paginas": int(grupo["paginas"].sum()), "caracteres": int(grupo["caracteres"].sum()),
            "segundos_total": round(float(grupo["segundos"].sum()), 6),
            "segundos_mediana": round(statistics.median(grupo["segundos"]), 6),
            "requiere_ocr": con_ocr, "pct_requiere_ocr": round(100 * con_ocr / ok, 1) if ok else 0.0,
        }

    filas = {tipo: resumir(grupo) for tipo, grupo in tabla.groupby("tipo", sort=True)}
    filas["TOTAL"] = resumir(tabla)
    return pd.DataFrame.from_dict(filas, orient="index")[columnas]
