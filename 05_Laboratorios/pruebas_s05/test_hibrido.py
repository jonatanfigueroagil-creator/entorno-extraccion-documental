"""Pruebas de extraccion/hibrido.py (no necesitan GPU)."""
from mi_pipeline.extraccion.hibrido import FASES, campos_ambiguos, combinar, evaluar_bandeja


def test_combinar_no_pisa_lo_que_salio_de_un_rotulo():
    campos, revisar, ambiguos = combinar({"ruc": "20992371634", "tcea": None}, {"ruc": "20990944050", "tcea": 22.34}, "RUC 20992371634 TCEA 22.34 %")
    assert campos == {"ruc": "20992371634", "tcea": 22.34} and revisar == [] and ambiguos == []


def test_combinar_manda_a_revisar_lo_que_no_figura_en_el_texto():
    campos, revisar, _ = combinar({"fecha": None}, {"fecha": "2021-04-18"}, "Fecha: 26/03/2026")
    assert campos["fecha"] is None and revisar == [{"campo": "fecha", "valor": "2021-04-18", "causa": "no figura en el texto"}]


def test_son_ambiguos_los_campos_que_lleno_el_pln():
    assert campos_ambiguos({"ruc": "1", "entidad": None, "fecha": None}, {"ruc": "1", "entidad": "Banco X DEMO S.A.", "fecha": None}) == ["entidad"]


def test_el_modelo_resuelve_un_campo_ambiguo_y_queda_anotado():
    texto = "Aseguradora: Seguros Sur DEMO S.A."
    campos, revisar, ambiguos = combinar({"aseguradora": "Aseguradora Seguros Sur DEMO S.A."}, {"aseguradora": "Seguros Sur DEMO S.A."}, texto, ["aseguradora"])
    assert campos["aseguradora"] == "Seguros Sur DEMO S.A." and revisar == []
    assert ambiguos == [{"campo": "aseguradora", "regla": "Aseguradora Seguros Sur DEMO S.A.", "modelo": "Seguros Sur DEMO S.A."}]


def test_un_campo_ambiguo_conserva_la_regla_si_el_modelo_no_se_comprueba():
    texto = "Aseguradora: Seguros Sur DEMO S.A."
    campos, revisar, ambiguos = combinar({"aseguradora": "Seguros Sur DEMO S.A."}, {"aseguradora": "Seguros Norte DEMO S.A."}, texto, ["aseguradora"])
    assert campos["aseguradora"] == "Seguros Sur DEMO S.A." and ambiguos == [] and revisar[0]["causa"] == "no figura en el texto"


def test_evaluar_bandeja_mide_cada_fase_con_la_misma_vara():
    resultado = {"archivo": "X-0001.pdf", "tipo": "poliza", "segundos": {fase: 0.0 for fase in FASES},
                 "fases": {fase: {"dni": None if fase == "1_ingesta" else "99000001"} for fase in FASES}}
    evaluacion = evaluar_bandeja([resultado], {"X-0001": {"dni": "99000001"}}, lambda valor, correcto: valor == correcto)
    assert [fila["correctos"] for fila in evaluacion["por_fase"]] == [0, 1, 1, 1, 1]
