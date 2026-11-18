"""Configuración de la ejecución de un lote: el YAML se lee con ``safe_load`` y se valida antes de procesar.

Lo que cambia de una corrida a otra (modo, trabajadores, etapas, carpetas) vive en ``config/pipeline.yaml``, no en el código.
Cada sección nueva tiene su modelo de Pydantic con ``extra="forbid"``: una clave mal escrita (``trabajdores``) detiene
el pipeline con un mensaje claro, antes de tocar un solo documento. Las secciones de S03 a S05 pasan sin cambios.
"""
from __future__ import annotations

from difflib import get_close_matches
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

RUTA_CONFIG = Path(__file__).resolve().parents[1] / "config" / "pipeline.yaml"
ORDEN = ("control", "ingesta", "ocr", "pln")  # el único orden válido de las etapas


class ErrorConfiguracion(ValueError):
    """El YAML no cumple el contrato: el mensaje dice qué clave falla y por qué."""


class Seccion(BaseModel):
    """Base de las secciones de S06: una clave que el modelo no conoce se rechaza."""

    model_config = ConfigDict(extra="forbid")


class Orquestacion(Seccion):
    """Cómo se ejecuta el lote."""

    modo: Literal["secuencial", "procesos"] = "procesos"
    trabajadores: int = Field(4, ge=1, le=61)
    etapas: list[Literal["control", "ingesta", "ocr", "pln"]] = list(ORDEN)
    motor_ocr: Literal["tesseract"] = "tesseract"
    tipo_por_prefijo: dict[str, str] = {}

    @model_validator(mode="after")
    def _etapas_en_orden(self) -> "Orquestacion":
        if self.etapas != [etapa for etapa in ORDEN if etapa in self.etapas]:
            raise ValueError("las etapas van sin repetir y en este orden: control, ingesta, ocr, pln")
        if ("ocr" in self.etapas or "pln" in self.etapas) and "ingesta" not in self.etapas:
            raise ValueError("las etapas ocr y pln necesitan la salida de la etapa ingesta")
        return self


class Reintentos(Seccion):
    """Cuántas veces se repite una operación ante un error transitorio y cuánto se espera antes de cada repetición."""

    intentos: int = Field(3, ge=0, le=10)
    espera_s: list[float] = [1, 2, 4]


class Cuarentena(Seccion):
    """Dónde se aparta lo que no se pudo procesar."""

    carpeta: str = "cuarentena"


class Almacenamiento(Seccion):
    """Dónde quedan la base, los Parquet y el reporte."""

    duckdb: str = "salidas/resultados.duckdb"
    parquet: str = "salidas/parquet"
    reporte: str = "salidas/reporte.html"


class Config(BaseModel):
    """La configuración completa: las cuatro secciones de S06 validadas y las de S03 a S05 tal como están."""

    model_config = ConfigDict(extra="allow")

    orquestacion: Orquestacion
    reintentos: Reintentos
    cuarentena: Cuarentena
    almacenamiento: Almacenamiento

    def en_carpeta(self, salida: str | Path) -> "Config":
        """Copia de la configuración con todas las salidas (base, Parquet, reporte y cuarentena) dentro de ``salida``."""
        salida = Path(salida)
        almacen = self.almacenamiento
        return self.model_copy(update={
            "almacenamiento": Almacenamiento(duckdb=str(salida / Path(almacen.duckdb).name), parquet=str(salida / Path(almacen.parquet).name),
                                             reporte=str(salida / Path(almacen.reporte).name)),
            "cuarentena": Cuarentena(carpeta=str(salida / Path(self.cuarentena.carpeta).name)),
        })

    def con(self, **cambios: Any) -> "Config":
        """Copia de la configuración con otros valores en ``orquestacion`` (``modo``, ``trabajadores``, ``etapas``), ya validados."""
        return self.model_copy(update={"orquestacion": Orquestacion(**{**self.orquestacion.model_dump(), **cambios})})


def _explicar(error: ValidationError) -> str:
    """Los errores de Pydantic en una línea cada uno y en palabras llanas."""
    lineas = []
    for detalle in error.errors():
        lugar = ".".join(str(parte) for parte in detalle["loc"])
        if detalle["type"] == "extra_forbidden":
            seccion = {"orquestacion": Orquestacion, "reintentos": Reintentos, "cuarentena": Cuarentena, "almacenamiento": Almacenamiento}.get(str(detalle["loc"][0]))
            parecidas = get_close_matches(str(detalle["loc"][-1]), list(seccion.model_fields) if seccion else [], n=1)
            pista = f" ¿Se quiso escribir '{parecidas[0]}'?" if parecidas else ""
            lineas.append(f"{lugar}: clave desconocida.{pista}")
        elif detalle["type"] == "missing":
            lineas.append(f"{lugar}: falta esta sección o clave.")
        else:
            lineas.append(f"{lugar}: valor no válido ({detalle['msg']}).")
    return "\n".join(lineas)


def cargar_config(ruta: str | Path | None = None) -> Config:
    """Lee el YAML y lo valida; si algo no cumple, se detiene aquí y no en medio del lote.

    Args:
        ruta: archivo YAML; por defecto, ``config/pipeline.yaml`` del paquete.

    Returns:
        La configuración validada (``cfg.orquestacion.trabajadores``, ``cfg.almacenamiento.duckdb``…).

    Raises:
        ErrorConfiguracion: con una línea por cada clave desconocida, ausente o con un valor no válido.
    """
    ruta = Path(ruta) if ruta else RUTA_CONFIG
    with open(ruta, encoding="utf-8") as archivo:
        datos = yaml.safe_load(archivo)
    try:
        return Config.model_validate(datos)
    except ValidationError as error:
        raise ErrorConfiguracion(f"{ruta.name} no es válido:\n{_explicar(error)}") from None
