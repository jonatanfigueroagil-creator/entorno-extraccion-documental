"""Preparación de la imagen antes del OCR: gris, paso a blanco y negro, ruido e inclinación."""
from __future__ import annotations

import cv2
import numpy as np


def a_gris(imagen: np.ndarray) -> np.ndarray:
    """Pasa una imagen RGB a escala de grises (si ya es gris, la devuelve igual)."""
    if imagen.ndim == 2:
        return imagen
    return cv2.cvtColor(imagen[:, :, :3], cv2.COLOR_RGB2GRAY)


def otsu(gris: np.ndarray) -> np.ndarray:
    """Pasa a blanco y negro con el umbral de Otsu, tras un suavizado leve."""
    suave = cv2.GaussianBlur(gris, (5, 5), 0)
    _, binaria = cv2.threshold(suave, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binaria


def adaptativa(gris: np.ndarray, bloque: int = 31, constante: int = 15) -> np.ndarray:
    """Pasa a blanco y negro con un umbral que cambia por zona (útil con sombras)."""
    return cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, bloque, constante)


def mediana(gris: np.ndarray, tamano: int = 3) -> np.ndarray:
    """Quita el ruido de píxeles sueltos (sal y pimienta) con un filtro de mediana."""
    return cv2.medianBlur(gris, tamano)


def estimar_inclinacion(gris: np.ndarray, maximo: float = 10.0, paso: float = 0.25) -> float:
    """Mide cuántos grados está girado el documento con el perfil de proyección.

    Gira una copia reducida de la tinta entre -maximo y +maximo grados. Cuando las líneas de texto quedan
    horizontales, la suma de tinta por fila alterna filas muy llenas y filas vacías: esa variación es máxima.

    Args:
        gris: imagen en escala de grises.
        maximo: giro máximo que se prueba, en grados (hacia cada lado).
        paso: separación entre ángulos probados, en grados.

    Returns:
        Inclinación del documento en grados (positivo = girado en sentido antihorario).
    """
    factor = 1000 / max(gris.shape)
    reducida = cv2.resize(gris, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
    tinta = cv2.adaptiveThreshold(reducida, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 15)
    alto, ancho = tinta.shape
    mejor_angulo, mejor_varianza = 0.0, -1.0
    for angulo in np.arange(-maximo, maximo + paso / 2, paso):
        matriz = cv2.getRotationMatrix2D((ancho / 2, alto / 2), float(angulo), 1.0)
        girada = cv2.warpAffine(tinta, matriz, (ancho, alto), flags=cv2.INTER_NEAREST)
        varianza = girada.sum(axis=1, dtype=np.float64).var()
        if varianza > mejor_varianza:
            mejor_angulo, mejor_varianza = float(angulo), varianza
    return 0.0 - mejor_angulo


def corregir_inclinacion(imagen: np.ndarray, maximo: float = 10.0, paso: float = 0.25) -> tuple[np.ndarray, float]:
    """Endereza la imagen: mide la inclinación y la gira en sentido contrario.

    Args:
        imagen: imagen en gris o RGB.
        maximo: giro máximo que se prueba, en grados.
        paso: separación entre ángulos probados, en grados.

    Returns:
        La imagen enderezada y la inclinación que tenía, en grados.
    """
    inclinacion = estimar_inclinacion(a_gris(imagen), maximo, paso)
    alto, ancho = imagen.shape[:2]
    matriz = cv2.getRotationMatrix2D((ancho / 2, alto / 2), -inclinacion, 1.0)
    recta = cv2.warpAffine(imagen, matriz, (ancho, alto), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return recta, inclinacion


RECETAS = ("crudo", "gris", "otsu", "adaptativa", "mediana")


def aplicar_receta(imagen: np.ndarray, receta: str) -> np.ndarray:
    """Aplica una receta de limpieza de la imagen: crudo, gris, otsu, adaptativa o mediana.

    La receta ``mediana`` quita el ruido de píxeles sueltos con un filtro de mediana de 5 y después pasa a blanco y negro como ``adaptativa``.

    Raises:
        ValueError: si la receta no existe.
    """
    if receta == "crudo":
        return imagen
    gris = a_gris(imagen)
    if receta == "gris":
        return gris
    if receta == "otsu":
        return otsu(gris)
    if receta == "adaptativa":
        return adaptativa(gris)
    if receta == "mediana":
        return adaptativa(mediana(gris, 5))
    raise ValueError(f"Receta desconocida: {receta}. Opciones: {', '.join(RECETAS)}")


def ampliar(imagen: np.ndarray, factor: int = 3) -> np.ndarray:
    """Agranda la imagen ``factor`` veces (útil con fotos de baja resolución)."""
    return cv2.resize(imagen, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)
