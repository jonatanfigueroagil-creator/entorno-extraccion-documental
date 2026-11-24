"""Esquemas de salida (Pydantic) por tipo de documento: el contrato de datos que el LLM debe cumplir.

Cada campo es obligatorio y admite ``null``: ``Field(...)`` obliga al modelo a escribir todas las claves y
le permite decir «no está». Las listas cerradas (``Literal``) fijan la moneda, la unidad y el motivo.
La descripción de cada campo es la que la parte FORMATO del prompt escribe para el modelo (``prompts.formato``);
Python normaliza después las fechas y los montos.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Moneda = Literal["PEN", "USD"]
Unidad = Literal["soles", "miles de soles", "millones de soles"]
Motivo = Literal["cobro indebido", "consumo no reconocido", "demora en entrega", "cargo duplicado", "cuenta cerrada", "tasa distinta"]
NUMERO = "como número, sin separadores de miles"
MONEDA = "código de la moneda: PEN (soles) o USD (dólares)"


class Poliza(BaseModel):
    """Póliza de seguro."""

    numero_poliza: str | None = Field(..., description="número de la póliza")
    aseguradora: str | None = Field(..., description="aseguradora que emite la póliza")
    ruc: str | None = Field(..., description="RUC de la aseguradora (11 cifras)")
    asegurado: str | None = Field(..., description="nombre y apellidos del asegurado")
    dni: str | None = Field(..., description="DNI del asegurado (8 cifras)")
    ramo: str | None = Field(..., description="ramo del seguro")
    suma_asegurada: float | None = Field(..., description=f"suma asegurada, {NUMERO}")
    prima_anual: float | None = Field(..., description=f"prima anual, {NUMERO}")
    moneda: Moneda | None = Field(..., description=MONEDA)
    vigencia_desde: str | None = Field(..., description="fecha de inicio de la vigencia")
    vigencia_hasta: str | None = Field(..., description="fecha de fin de la vigencia")
    beneficiario: str | None = Field(..., description="nombre y apellidos del beneficiario")
    deducible_pct: float | None = Field(..., description=f"deducible en porcentaje, {NUMERO}")


class Contrato(BaseModel):
    """Contrato de crédito."""

    numero_contrato: str | None = Field(..., description="número del contrato")
    fecha_contrato: str | None = Field(..., description="fecha de firma del contrato (no la de una cuota)")
    entidad: str | None = Field(..., description="entidad financiera que otorga el crédito")
    ruc: str | None = Field(..., description="RUC de la entidad (11 cifras)")
    cliente: str | None = Field(..., description="nombre y apellidos del cliente")
    dni_cliente: str | None = Field(..., description="DNI del cliente (8 cifras)")
    monto: float | None = Field(..., description=f"monto del crédito, {NUMERO}")
    moneda: Moneda | None = Field(..., description=MONEDA)
    plazo_meses: float | None = Field(..., description=f"plazo en meses, {NUMERO}")
    tea: float | None = Field(..., description="tasa efectiva anual (TEA) en porcentaje, como número")
    tcea: float | None = Field(..., description="tasa de costo efectivo anual (TCEA) en porcentaje, como número")
    penalidad_mora_diaria_pct: float | None = Field(..., description="penalidad por mora diaria en porcentaje, como número")
    cuota_mensual: float | None = Field(..., description=f"cuota mensual, {NUMERO}")
    cuenta_cargo: str | None = Field(..., description="cuenta de cargo")
    cci: str | None = Field(..., description="código de cuenta interbancario (CCI)")


class Oficio(BaseModel):
    """Oficio de la Autoridad Supervisora DEMO a una entidad supervisada."""

    numero_oficio: str | None = Field(..., description="número del oficio")
    fecha: str | None = Field(..., description="fecha del oficio")
    entidad: str | None = Field(..., description="entidad supervisada a la que se dirige el oficio (no la autoridad que lo emite)")
    ruc: str | None = Field(..., description="RUC de la entidad supervisada (11 cifras)")
    asunto: str | None = Field(..., description="asunto del oficio")
    referencia: str | None = Field(..., description="referencia del oficio")
    plazo_dias: float | None = Field(..., description="plazo en días, como número")
    emisor: str | None = Field(..., description="órgano o intendencia que emite el oficio")
    firmante: str | None = Field(..., description="nombre y apellidos de quien firma")
    cargo: str | None = Field(..., description="cargo de quien firma")


class EstadoFinanciero(BaseModel):
    """Estado de situación financiera."""

    entidad: str | None = Field(..., description="entidad que presenta el estado financiero")
    ruc: str | None = Field(..., description="RUC de la entidad (11 cifras)")
    periodo: str | None = Field(..., description="fecha de cierre del periodo")
    moneda: Moneda | None = Field(..., description=MONEDA)
    unidad: Unidad | None = Field(..., description="unidad en que se expresan las cifras")
    total_activo: float | None = Field(..., description=f"total activo, {NUMERO}")
    total_pasivo: float | None = Field(..., description=f"total pasivo, {NUMERO}")
    total_patrimonio: float | None = Field(..., description=f"total patrimonio, {NUMERO}")
    utilidad_neta: float | None = Field(..., description=f"utilidad neta, {NUMERO}")


class Voucher(BaseModel):
    """Comprobante de depósito."""

    entidad: str | None = Field(..., description="entidad financiera del comprobante")
    numero_operacion: str | None = Field(..., description="número de operación")
    fecha: str | None = Field(..., description="fecha de la operación")
    hora: str | None = Field(..., description="hora de la operación (HH:MM)")
    monto: float | None = Field(..., description=f"monto depositado, {NUMERO}")
    moneda: Moneda | None = Field(..., description=MONEDA)
    cuenta_destino: str | None = Field(..., description="cuenta de destino")
    titular: str | None = Field(..., description="nombre y apellidos del titular de la cuenta")
    depositante: str | None = Field(..., description="nombre y apellidos de quien deposita")
    dni_depositante: str | None = Field(..., description="DNI de quien deposita (8 cifras)")


class Reclamo(BaseModel):
    """Reclamo de un cliente (correo y adjunto)."""

    numero_reclamo: str | None = Field(..., description="número del reclamo; null si no aparece en el texto")
    fecha: str | None = Field(..., description="fecha del cargo reclamado")
    nombre: str | None = Field(..., description="nombre y apellidos del cliente")
    dni: str | None = Field(..., description="DNI del cliente (8 cifras)")
    entidad: str | None = Field(..., description="entidad financiera reclamada")
    producto: str | None = Field(..., description="producto financiero")
    motivo: Motivo | None = Field(..., description="motivo del reclamo")
    monto_reclamado: float | None = Field(..., description=f"monto reclamado en soles, {NUMERO}")
    telefono: str | None = Field(..., description="teléfono del cliente")
    correo: str | None = Field(..., description="correo electrónico del cliente")


class Tarifario(BaseModel):
    """Tarifario de tasas y comisiones."""

    entidad: str | None = Field(..., description="entidad que publica el tarifario")
    ruc: str | None = Field(..., description="RUC de la entidad (11 cifras)")
    vigencia: str | None = Field(..., description="fecha desde la que rige el tarifario")
    n_productos: float | None = Field(..., description="cantidad de productos distintos del tarifario, como número")


class Expediente(BaseModel):
    """Expediente de autorización (documento largo)."""

    numero_expediente: str | None = Field(..., description="número del expediente")
    entidad: str | None = Field(..., description="entidad que presenta el expediente")
    ruc: str | None = Field(..., description="RUC de la entidad (11 cifras)")
    tipo_expediente: str | None = Field(..., description="tipo de trámite del expediente, en una palabra")
    fecha_presentacion: str | None = Field(..., description="fecha de presentación del expediente")


ESQUEMAS: dict[str, type[BaseModel]] = {
    "poliza": Poliza, "contrato": Contrato, "oficio": Oficio, "estado_financiero": EstadoFinanciero,
    "voucher": Voucher, "reclamo": Reclamo, "tarifario": Tarifario, "expediente": Expediente,
}


def campos_de(tipo: str) -> list[str]:
    """Nombres de los campos que se extraen de un tipo de documento, en el orden del esquema."""
    return list(ESQUEMAS[tipo].model_fields)
