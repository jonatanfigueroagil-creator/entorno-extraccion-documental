"""Pruebas del limpieza de la imagen."""
import cv2
import numpy as np

from mi_pipeline.ocr.preprocesar import a_gris, corregir_inclinacion


def hoja_con_lineas(angulo: float = 0.0) -> np.ndarray:
    """Hoja blanca con 12 renglones de texto, girada ``angulo`` grados (positivo = antihorario)."""
    hoja = np.full((1000, 800, 3), 255, np.uint8)
    for fila in range(12):
        cv2.putText(hoja, "Oficio de supervision DEMO 2026", (60, 120 + fila * 60), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
    matriz = cv2.getRotationMatrix2D((400, 500), angulo, 1.0)
    return cv2.warpAffine(hoja, matriz, (800, 1000), borderValue=(255, 255, 255))


def test_a_gris_pasa_de_tres_canales_a_uno():
    assert a_gris(hoja_con_lineas()).shape == (1000, 800)


def test_corregir_inclinacion_mide_el_giro_con_error_menor_a_medio_grado():
    _, inclinacion = corregir_inclinacion(hoja_con_lineas(5.0))
    assert abs(inclinacion - 5.0) < 0.5
