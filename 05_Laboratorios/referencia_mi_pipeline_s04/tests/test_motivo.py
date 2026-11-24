"""Pruebas de clasificacion/motivo.py."""
from mi_pipeline.clasificacion.motivo import crear_modelo, entrenar, predecir, validar_cruzado

FRASES = {
    "cobro indebido": "me cobraron una comision que nunca autorice",
    "cargo duplicado": "me descontaron dos veces la misma cuota",
    "demora en entrega": "pedi mi tarjeta hace semanas y nadie me la entrega",
    "cuenta cerrada": "cerraron mi cuenta sin avisarme y no me devuelven mi saldo",
}
TEXTOS = [f"{frase} en la agencia numero {i}" for i in range(5) for frase in FRASES.values()]
ETIQUETAS = [etiqueta for _ in range(5) for etiqueta in FRASES]


def test_crear_modelo_usa_tfidf_de_uno_y_dos_terminos():
    assert crear_modelo().named_steps["tfidf"].ngram_range == (1, 2)


def test_predecir_devuelve_el_motivo_y_su_probabilidad():
    assert predecir(entrenar(TEXTOS, ETIQUETAS), ["cerraron mi cuenta sin avisarme"])[0][0] == "cuenta cerrada"


def test_validar_cruzado_da_un_f1_macro_alto_con_frases_claras():
    assert validar_cruzado(TEXTOS, ETIQUETAS)["f1_macro"] >= 0.9
