"""Pruebas de calidad/alucinaciones.py (no necesitan GPU)."""
from mi_pipeline.calidad.alucinaciones import a_revisar, aparece, validar_campo


def test_aparece_halla_un_monto_con_comas_y_una_fecha_escrita():
    assert aparece(39317.0, "Total activo 39,317") and aparece("2026-06-24", "Lima, 24 de junio de 2026")


def test_aparece_marca_una_unidad_inventada():
    assert not aparece("millones de soles", "Estado de situacion financiera (en soles)")


def test_los_validadores_rechazan_tea_mayor_que_tcea_un_emisor_persona_y_una_moneda_sin_codigo():
    assert not validar_campo("tea", 22.34, {"tcea": 22.34}) and validar_campo("tea", 20.81, {"tcea": 22.34})
    assert not validar_campo("emisor", "Ana Ruiz Soto", {})
    assert not validar_campo("moneda", "S/", {}) and validar_campo("moneda", "PEN", {})


def test_a_revisar_dice_la_causa():
    assert a_revisar("fecha", "2021-04-18", "Fecha: 26/03/2026", {}) == "no figura en el texto"
    assert a_revisar("fecha", "2026-03-26", "Fecha: 26/03/2026", {}) is None
