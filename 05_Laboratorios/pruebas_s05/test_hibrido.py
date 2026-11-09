"""Pruebas de extraccion/hibrido.py (no necesitan GPU)."""
from mi_pipeline.extraccion.hibrido import FASES, combinar, evaluar_bandeja


def test_combinar_no_pisa_lo_que_dieron_las_fases_anteriores():
    campos, revisar = combinar({"ruc": "20992371634", "tcea": None}, {"ruc": "20990944050", "tcea": 22.34}, "RUC 20992371634 TCEA 22.34 %")
    assert campos == {"ruc": "20992371634", "tcea": 22.34} and revisar == []


def test_combinar_manda_a_revisar_lo_que_no_figura_en_el_texto():
    campos, revisar = combinar({"fecha": None}, {"fecha": "2021-04-18"}, "Fecha: 26/03/2026")
    assert campos["fecha"] is None and revisar == [{"campo": "fecha", "valor": "2021-04-18", "causa": "no figura en el texto"}]


def test_evaluar_bandeja_mide_cada_fase_con_la_misma_vara():
    resultado = {"archivo": "X-0001.pdf", "tipo": "poliza", "segundos": {fase: 0.0 for fase in FASES},
                 "fases": {fase: {"dni": None if fase == "1_ingesta" else "99000001"} for fase in FASES}}
    evaluacion = evaluar_bandeja([resultado], {"X-0001": {"dni": "99000001"}}, lambda valor, correcto: valor == correcto)
    assert [fila["correctos"] for fila in evaluacion["por_fase"]] == [0, 1, 1, 1, 1]
