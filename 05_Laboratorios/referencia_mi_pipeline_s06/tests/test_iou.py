"""Pruebas de la intersección sobre unión (iou)."""
import pytest

from mi_pipeline.calidad.metricas import iou


def test_iou_cajas_identicas():
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_iou_cajas_a_medias():
    assert iou((0, 0, 10, 10), (5, 0, 15, 10)) == pytest.approx(1 / 3)


def test_iou_cajas_sin_cruce():
    assert iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
