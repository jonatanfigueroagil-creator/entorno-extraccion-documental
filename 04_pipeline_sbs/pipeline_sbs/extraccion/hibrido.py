"""Cadena completa de un archivo: Ingesta -> OCR -> PLN -> LLM. Cada fase usa lo anterior y agrega lo suyo.

Técnica: el LLM como respaldo. Primero lo que es repetible y dice de dónde sale cada valor; el modelo solo para lo vacío y lo ambiguo.
1 Ingesta: lector por formato, campos rotulados y normalización.
2 OCR: lo que no trae capa de texto se lee con ``glm-ocr`` (o Tesseract) y se repite la fase 1.
3 PLN: las reglas y el NER de S04 completan lo que falta.
4 LLM: el modelo, con el prompt del E3 (Rol, Contexto, Tarea, Formato y un ejemplo), llena lo que sigue vacío y revisa los
  campos ambiguos (los que dedujo la fase 3 sin un rótulo que los respalde); lo que salió de un rótulo no se toca.
  Su valor entra si figura en el texto y pasa los validadores; si no, va a la lista «revisar». Si cambia un campo ambiguo,
  el cambio queda anotado en la lista «ambiguos».
"""
from __future__ import annotations

import logging  # solo referencia
import time
from pathlib import Path
from typing import Any, Callable, Collection

from ..calidad.alucinaciones import a_revisar
from ..ingesta.leer_documento import FormatoNoSoportado, aplicar_ocr, campos_rotulados, leer_documento, plano, texto_de
from ..llm.cliente_llm import configuracion_llm
from ..llm.esquemas import campos_de
from ..llm.extraer import extraer_con_llm
from . import montos, reglas
from .ner import ner_spacy

FASES = ("1_ingesta", "2_ocr", "3_pln", "4_llm", "solo_llm")
REGLAS_POR_CAMPO = {
    "dni": reglas.extraer_dni, "dni_cliente": reglas.extraer_dni, "dni_depositante": reglas.extraer_dni,
    "ruc": reglas.extraer_ruc, "numero_oficio": reglas.extraer_numero_oficio, "telefono": reglas.extraer_telefono,
    "correo": reglas.extraer_correo_electronico, "producto": reglas.extraer_producto, "nombre": reglas.extraer_nombre,
    "entidad": reglas.extraer_entidad, "aseguradora": reglas.extraer_entidad,
}
registro = logging.getLogger(__name__)  # solo referencia


def pln(tipo: str, doc: dict[str, Any], previo: dict[str, Any]) -> dict[str, Any]:
    """Fase 3: las reglas de S04 y el NER de spaCy completan los campos que la ingesta dejó vacíos."""
    texto = texto_de(doc)
    corrido = " ".join(texto.split())
    campos = dict(previo)
    for campo, regla in REGLAS_POR_CAMPO.items():
        if campo in campos and campos[campo] is None:
            campos[campo] = regla(corrido)
    for campo in ("fecha", "vigencia"):
        if campo in campos and campos[campo] is None and tipo != "reclamo":
            campos[campo] = reglas.extraer_fecha(texto)
    if tipo == "reclamo":
        campos["motivo"] = reglas.extraer_motivo(texto) or campos.get("motivo")
        campos["fecha"] = reglas.extraer_fecha(texto)
        campos["monto_reclamado"] = montos.extraer_monto(corrido)
    if campos.get("firmante", "") is None or campos.get("cliente", "") is None:
        personas = [e["texto"] for e in ner_spacy(corrido[:20000]) if e["etiqueta"] == "PER" and len(e["texto"].split()) >= 2]
        if "firmante" in campos and campos["firmante"] is None and personas:
            campos["firmante"] = personas[-1]
        if "cliente" in campos and campos["cliente"] is None and personas:
            campos["cliente"] = personas[0]
    return campos


def campos_ambiguos(con_rotulo: dict[str, Any], con_pln: dict[str, Any]) -> list[str]:
    """Los campos ambiguos: los que llenó o cambió la fase 3 (una regla o el NER), sin un rótulo del documento que los respalde."""
    return [campo for campo, valor in con_pln.items() if valor is not None and valor != con_rotulo.get(campo)]


def combinar(previo: dict[str, Any], del_llm: dict[str, Any], texto: str,
             dudosos: Collection[str] = ()) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Fase 4, el LLM como respaldo: lo firme no se toca; el LLM llena lo vacío y resuelve lo dudoso.

    Su valor entra solo si figura en el texto y pasa los validadores.

    Returns:
        Los campos, la lista «revisar» (valores del LLM rechazados, con su causa) y la lista «ambiguos»
        (campos dudosos en que la regla y el modelo no coinciden y entró el valor del modelo).
    """
    campos, revisar, ambiguos = dict(previo), [], []
    for campo, valor in del_llm.items():
        actual = campos.get(campo)
        if valor is None or (actual is not None and (campo not in dudosos or plano(str(actual)) == plano(str(valor)))):
            continue
        causa = a_revisar(campo, valor, texto, campos)
        if causa is not None:
            revisar.append({"campo": campo, "valor": valor, "causa": causa})
            continue
        if actual is not None:
            ambiguos.append({"campo": campo, "regla": actual, "modelo": valor})
        campos[campo] = valor
    return campos, revisar, ambiguos


def cadena(ruta: str | Path, tipo: str, modelo: str | None = None, motor_ocr: str = "glm",
           cfg: dict[str, Any] | None = None, comparar: bool = True) -> dict[str, Any]:
    """Procesa un archivo con las cuatro fases y guarda lo que da cada una.

    Args:
        comparar: si es True, llama al modelo aunque la fase 4 no lo necesite, para medir el LLM solo.

    Returns:
        ``archivo``, ``tipo``, ``fases`` (campos después de cada fase y los del LLM solo), ``segundos`` por fase,
        ``revisar`` (valores del LLM rechazados), ``ambiguos`` (campos resueltos por el modelo), ``llamo_modelo`` (si la fase 4
        lo necesitó), ``paginas_ocr`` y ``texto`` (el que vio el LLM).
    """
    cfg = cfg or configuracion_llm()
    campos = campos_de(tipo)
    fases, segundos = {}, {}
    inicio = time.perf_counter()
    doc = leer_documento(ruta)
    rotulados = campos_rotulados(tipo, doc)
    fases["1_ingesta"] = {c: rotulados.get(c) for c in campos}
    segundos["1_ingesta"] = time.perf_counter() - inicio
    inicio = time.perf_counter()
    if doc["pendientes"]:
        doc = aplicar_ocr(doc, motor=motor_ocr, cfg=cfg)
        rotulados = campos_rotulados(tipo, doc)
    fases["2_ocr"] = {c: rotulados.get(c) for c in campos}
    segundos["2_ocr"] = time.perf_counter() - inicio
    inicio = time.perf_counter()
    fases["3_pln"] = pln(tipo, doc, fases["2_ocr"])
    segundos["3_pln"] = time.perf_counter() - inicio
    texto = texto_de(doc)
    dudosos = campos_ambiguos(fases["2_ocr"], fases["3_pln"])
    hace_falta = bool(dudosos) or any(valor is None for valor in fases["3_pln"].values())   # si todo es firme, no se llama al modelo
    del_llm = extraer_con_llm(texto, tipo, modelo, cfg=cfg) if hace_falta or comparar else {"campos": {c: None for c in campos}, "segundos": 0.0}
    fases["4_llm"], revisar, ambiguos = combinar(fases["3_pln"], del_llm["campos"], texto, dudosos) if hace_falta else (dict(fases["3_pln"]), [], [])
    fases["solo_llm"] = del_llm["campos"]
    segundos["4_llm"] = del_llm["segundos"] if hace_falta else 0.0
    segundos["solo_llm"] = del_llm["segundos"]
    for fase in FASES:  # solo referencia
        registro.info("fase", extra={"componente": "hibrido", "archivo": Path(ruta).name, "fase": fase,  # solo referencia
                                     "segundos": round(segundos[fase], 2), "campos": sum(v is not None for v in fases[fase].values())})  # solo referencia
    return {"archivo": Path(ruta).name, "tipo": tipo, "fases": fases, "segundos": segundos, "revisar": revisar, "ambiguos": ambiguos,
            "llamo_modelo": hace_falta, "paginas_ocr": len(doc["pendientes"]), "texto": texto}


def procesar_bandeja(bandeja: list[tuple[str | Path, str]], modelo: str | None = None, motor_ocr: str = "glm",
                     cfg: dict[str, Any] | None = None, comparar: bool = True) -> list[dict[str, Any]]:
    """Corre la cadena sobre cada ``(ruta, tipo)``. Un archivo con error no detiene la bandeja: queda con su error."""
    resultados = []
    for ruta, tipo in bandeja:
        try:
            resultados.append(cadena(ruta, tipo, modelo, motor_ocr, cfg, comparar))
        except (FormatoNoSoportado, OSError, ValueError) as error:
            resultados.append({"archivo": Path(ruta).name, "tipo": tipo, "error": f"{type(error).__name__}: {error}"})
            registro.warning("archivo_con_error", extra={"componente": "hibrido", "archivo": Path(ruta).name, "motivo": type(error).__name__})  # solo referencia
    return resultados


def evaluar_bandeja(resultados: list[dict[str, Any]], correctos: dict[str, dict[str, Any]],
                    es_correcto: Callable[[Any, Any], bool]) -> dict[str, list[dict[str, Any]]]:
    """Mide cada fase con la misma vara: correctos / esperados, precisión, exhaustividad y F1, en total y por tipo.

    Args:
        resultados: salida de ``procesar_bandeja`` (los archivos con error no se miden).
        correctos: respuesta correcta de cada archivo, por nombre sin extensión.
        es_correcto: función que dice si un valor extraído coincide con el correcto.

    Returns:
        ``por_fase`` (una fila por fase), ``por_tipo`` (correctos/esperados por tipo y fase) y ``por_archivo``.
    """
    por_archivo = []
    for r in resultados:
        if "error" in r:
            continue
        correcto = correctos[Path(r["archivo"]).stem]
        fila = {"archivo": r["archivo"], "tipo": r["tipo"], "esperados": len(correcto)}
        for fase in FASES:
            pred = r["fases"][fase]
            fila[fase] = sum(es_correcto(pred.get(c), v) for c, v in correcto.items())
            fila[f"{fase}_entregados"] = sum(pred.get(c) is not None for c in correcto)
            fila[f"{fase}_bien_entregados"] = sum(es_correcto(pred.get(c), v) for c, v in correcto.items() if pred.get(c) is not None)
            fila[f"{fase}_segundos"] = r["segundos"][fase]
        fila["no_nulos"] = sum(v is not None for v in correcto.values())
        por_archivo.append(fila)
    total = sum(f["esperados"] for f in por_archivo)
    por_fase = []
    for fase in FASES:
        bien = sum(f[fase] for f in por_archivo)
        entregados = sum(f[f"{fase}_entregados"] for f in por_archivo)
        bien_entregados = sum(f[f"{fase}_bien_entregados"] for f in por_archivo)
        precision = bien_entregados / max(entregados, 1)
        exhaustividad = bien_entregados / max(sum(f["no_nulos"] for f in por_archivo), 1)
        por_fase.append({"fase": fase, "correctos": bien, "esperados": total, "exactitud": round(bien / max(total, 1), 3),
                         "precision": round(precision, 3), "exhaustividad": round(exhaustividad, 3),
                         "f1": round(2 * precision * exhaustividad / max(precision + exhaustividad, 1e-9), 3),
                         "segundos": round(sum(f[f"{fase}_segundos"] for f in por_archivo), 1)})
    por_tipo = []
    for tipo in dict.fromkeys(f["tipo"] for f in por_archivo):
        filas = [f for f in por_archivo if f["tipo"] == tipo]
        esperados = sum(f["esperados"] for f in filas)
        por_tipo.append({"tipo": tipo, **{fase: f"{sum(f[fase] for f in filas)}/{esperados}" for fase in FASES}})
    return {"por_fase": por_fase, "por_tipo": por_tipo, "por_archivo": por_archivo}
