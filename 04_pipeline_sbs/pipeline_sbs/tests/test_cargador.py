"""Pruebas del cargador: un lote con los 6 modos de fallo termina, tipifica cada motivo y es idempotente."""
import json
from pathlib import Path

import pytest

from pipeline_sbs.ingesta.cargador import (
    CargadorDocumentos,
    calcular_sha256,
    detectar_formato,
    enviar_a_cuarentena,
    estadisticas,
    tabla_resultados,
    validar_formato_y_extension,
)
from pipeline_sbs.ingesta.errores import ErrorArchivoVacio, ErrorExtensionFalsa, ErrorFormatoNoSoportado

MOTIVOS_ESPERADOS = {
    "A03_extension_falsa.pdf": "extension_falsa",
    "A04_docx_corrupto.docx": "docx_corrupto",
    "A05_cifrado.pdf": "pdf_cifrado",
    "A06_truncado.pdf": "pdf_danado",
    "A07_vacio.pdf": "archivo_vacio",
}


def _cargar(lote: Path, cuarentena: Path):
    return CargadorDocumentos(lote, cuarentena, esperas=(0, 0, 0)).cargar_lote()


def test_el_lote_termina_con_un_registro_por_archivo(lote_trampas, tmp_path):
    resultados = _cargar(lote_trampas, tmp_path / "q")
    assert [r.archivo for r in resultados] == sorted(p.name for p in lote_trampas.iterdir())
    assert len(resultados) == 12


def test_cada_trampa_tiene_su_motivo_tipificado(lote_trampas, tmp_path):
    por_archivo = {r.archivo: r for r in _cargar(lote_trampas, tmp_path / "q")}
    for archivo, motivo in MOTIVOS_ESPERADOS.items():
        assert por_archivo[archivo].estado == "fallo", archivo
        assert por_archivo[archivo].motivo == motivo, archivo
    assert len({por_archivo[a].motivo for a in MOTIVOS_ESPERADOS}) == 5      # motivos distintos
    copia = por_archivo["A08_copia.pdf"]
    assert copia.estado == "duplicado" and copia.duplicado_de == "A01_nativo.pdf"
    assert copia.caracteres == 0 and copia.paginas == 0                       # no se reprocesó


def test_escaneado_e_imagen_son_ok_con_requiere_ocr(lote_trampas, tmp_path):
    por_archivo = {r.archivo: r for r in _cargar(lote_trampas, tmp_path / "q")}
    for archivo in ("A02_escaneado.pdf", "A12_voucher.png"):
        assert por_archivo[archivo].estado == "ok" and por_archivo[archivo].requiere_ocr, archivo
    for archivo in ("A01_nativo.pdf", "A09_contrato.docx", "A10_reclamo.eml", "A11_tarifario.html"):
        assert por_archivo[archivo].estado == "ok" and not por_archivo[archivo].requiere_ocr, archivo


def test_los_fallos_van_a_cuarentena_con_su_motivo_y_el_original_queda(lote_trampas, tmp_path):
    cuarentena = tmp_path / "q"
    _cargar(lote_trampas, cuarentena)
    copias = sorted(p.name for p in cuarentena.iterdir() if not p.name.endswith(".json"))
    assert copias == sorted(MOTIVOS_ESPERADOS)
    nota = json.loads((cuarentena / "A05_cifrado.pdf.motivo.json").read_text(encoding="utf-8"))
    assert nota["motivo"] == "pdf_cifrado"
    assert (lote_trampas / "A05_cifrado.pdf").exists()                         # se copia, no se mueve


def test_segunda_corrida_da_el_mismo_resultado(lote_trampas, tmp_path):
    cargador = CargadorDocumentos(lote_trampas, tmp_path / "q", esperas=(0, 0, 0))
    campos = ["archivo", "estado", "motivo", "formato", "paginas", "caracteres", "requiere_ocr", "sha256", "duplicado_de"]
    primera = tabla_resultados(cargador.cargar_lote())[campos]
    segunda = tabla_resultados(cargador.cargar_lote())[campos]
    assert primera.equals(segunda)
    assert sorted(p.name for p in (tmp_path / "q").iterdir()).count("A05_cifrado.pdf") == 1


def test_estadisticas_porcentaje_ocr_solo_sobre_archivos_ok(lote_trampas, tmp_path):
    tabla = estadisticas(_cargar(lote_trampas, tmp_path / "q"))
    pdf = tabla.loc["pdf"]
    # 7 PDF recibidos: nativo y escaneado ok, 4 fallos (extensión falsa, cifrado, truncado, vacío) y 1 duplicado
    assert pdf["n"] == 7 and pdf["ok"] == 2 and pdf["fallo"] == 4 and pdf["duplicado"] == 1
    assert pdf["requiere_ocr"] == 1 and pdf["pct_requiere_ocr"] == 50.0       # 1 de 2 ok, no 1 de 7
    total = tabla.loc["TOTAL"]
    assert total["n"] == 12 and total["ok"] + total["fallo"] + total["duplicado"] == 12


def test_cargar_uno_no_lanza_aunque_el_archivo_no_exista(tmp_path):
    resultado = CargadorDocumentos(tmp_path, tmp_path / "q", esperas=(0,)).cargar_uno(tmp_path / "fantasma.pdf")
    assert resultado.estado == "fallo" and resultado.motivo == "archivo_inaccesible"


def test_cargar_lote_en_carpeta_inexistente(tmp_path):
    with pytest.raises(NotADirectoryError):
        CargadorDocumentos(tmp_path / "no_existe", tmp_path / "q").cargar_lote()


def test_desde_configuracion_usa_los_valores_del_yaml(tmp_path):
    cargador = CargadorDocumentos.desde_configuracion(tmp_path)
    assert cargador.umbral_ocr == 20 and cargador.cuarentena == Path("cuarentena")
    assert CargadorDocumentos.desde_configuracion(tmp_path, cuarentena=tmp_path / "q").cuarentena == tmp_path / "q"


def test_detectar_formato_por_firma_y_no_por_extension(lote_trampas):
    assert detectar_formato(lote_trampas / "A03_extension_falsa.pdf") == "png"
    assert detectar_formato(lote_trampas / "A07_vacio.pdf") == "vacio"
    assert detectar_formato(lote_trampas / "A10_reclamo.eml") == "eml"
    assert detectar_formato(lote_trampas / "A11_tarifario.html") == "html"
    assert detectar_formato(lote_trampas / "A09_contrato.docx") == "docx"


def test_validar_formato_y_extension(lote_trampas, tmp_path):
    with pytest.raises(ErrorArchivoVacio):
        validar_formato_y_extension(lote_trampas / "A07_vacio.pdf", "vacio")
    with pytest.raises(ErrorExtensionFalsa):
        validar_formato_y_extension(lote_trampas / "A03_extension_falsa.pdf", "png")
    texto = tmp_path / "nota.pdf"
    texto.write_text("solo texto", encoding="utf-8")
    assert detectar_formato(texto) == "desconocido"
    with pytest.raises(ErrorFormatoNoSoportado):
        validar_formato_y_extension(texto, "desconocido")


def test_sha256_y_cuarentena_idempotente(lote_trampas, tmp_path):
    ruta = lote_trampas / "A01_nativo.pdf"
    assert calcular_sha256(ruta) == calcular_sha256(lote_trampas / "A08_copia.pdf")
    for _ in range(2):                                                         # repetir no falla ni duplica
        destino = enviar_a_cuarentena(ruta, tmp_path / "q", "prueba", "detalle")
    assert destino.read_bytes() == ruta.read_bytes()
    assert len(list((tmp_path / "q").iterdir())) == 2                          # copia + nota


def test_lote_real_de_practica(datos_practica, tmp_path):
    lote = datos_practica / "01_Lote_S02"
    if not lote.is_dir():
        pytest.skip("No está la carpeta 01_Lote_S02 en los datos de práctica")
    resultados = _cargar(lote, tmp_path / "q")
    assert len(resultados) == 20
    por_archivo = {r.archivo: r for r in resultados}
    assert por_archivo["LOT-0002.pdf"].motivo == "extension_falsa"
    assert por_archivo["LOT-0006.docx"].motivo == "docx_corrupto"
    assert por_archivo["LOT-0007.pdf"].motivo == "pdf_cifrado"
    assert por_archivo["LOT-0014.pdf"].motivo == "pdf_danado"
    assert por_archivo["LOT-0016.pdf"].motivo == "archivo_vacio"
    assert por_archivo["LOT-0019.pdf"].estado == "duplicado" and por_archivo["LOT-0019.pdf"].duplicado_de == "LOT-0001.pdf"
    assert por_archivo["LOT-0012.pdf"].estado == "ok" and por_archivo["LOT-0012.pdf"].requiere_ocr
