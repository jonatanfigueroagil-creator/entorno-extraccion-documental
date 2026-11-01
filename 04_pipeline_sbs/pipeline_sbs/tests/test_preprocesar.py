"""Pruebas de ocr.preprocesar: gris, paso a blanco y negro, ruido, inclinación y recetas."""
import cv2
import numpy as np
import pytest

from pipeline_sbs.ocr.preprocesar import (
    RECETAS,
    a_gris,
    adaptativa,
    ampliar,
    aplicar_receta,
    corregir_inclinacion,
    estimar_inclinacion,
    mediana,
    otsu,
)


def hoja_con_lineas(angulo: float = 0.0) -> np.ndarray:
    """Hoja blanca con 12 renglones de texto, girada ``angulo`` grados (positivo = antihorario)."""
    hoja = np.full((1000, 800, 3), 255, np.uint8)
    for fila in range(12):
        cv2.putText(hoja, "Oficio de supervision DEMO 2026", (60, 120 + fila * 60), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 0), 2)
    matriz = cv2.getRotationMatrix2D((400, 500), angulo, 1.0)
    return cv2.warpAffine(hoja, matriz, (800, 1000), borderValue=(255, 255, 255))


def test_a_gris_pasa_de_tres_canales_a_uno():
    assert a_gris(hoja_con_lineas()).shape == (1000, 800)


def test_otsu_solo_deja_blanco_y_negro():
    assert set(np.unique(otsu(a_gris(hoja_con_lineas())))) == {0, 255}


def test_adaptativa_solo_deja_blanco_y_negro():
    assert set(np.unique(adaptativa(a_gris(hoja_con_lineas())))) == {0, 255}


def test_mediana_quita_puntos_aislados():
    gris = np.full((50, 50), 255, np.uint8)
    gris[10, 10] = 0
    assert mediana(gris)[10, 10] == 255


@pytest.mark.parametrize("angulo", [-6.0, -2.0, 3.0, 8.0])
def test_estimar_inclinacion_con_error_menor_a_medio_grado(angulo):
    estimado = estimar_inclinacion(a_gris(hoja_con_lineas(angulo)))
    assert abs(estimado - angulo) < 0.5


def test_corregir_inclinacion_endereza_la_hoja():
    imagen = hoja_con_lineas(5.0)
    recta, inclinacion = corregir_inclinacion(imagen)
    assert recta.shape == imagen.shape
    assert abs(inclinacion - 5.0) < 0.5
    assert abs(estimar_inclinacion(a_gris(recta))) < 0.5


def test_aplicar_receta_devuelve_la_forma_esperada():
    imagen = hoja_con_lineas()
    assert aplicar_receta(imagen, "crudo").shape == imagen.shape
    for receta in [r for r in RECETAS if r != "crudo"]:
        assert aplicar_receta(imagen, receta).shape == (1000, 800)


def test_aplicar_receta_desconocida():
    with pytest.raises(ValueError, match="Receta desconocida"):
        aplicar_receta(hoja_con_lineas(), "magica")


def test_ampliar_triplica_el_tamano():
    assert ampliar(np.zeros((10, 20), np.uint8), 3).shape == (30, 60)
