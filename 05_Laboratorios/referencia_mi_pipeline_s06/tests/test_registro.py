"""Pruebas de orquestacion/registro.py (no necesitan Tesseract ni un modelo de lenguaje)."""
import json

import pytest

from mi_pipeline.orquestacion.registro import a_cuarentena, abrir_registro, huella, marcar, reintentar, ya_procesado


def test_la_huella_depende_del_contenido_y_no_del_nombre(tmp_path):
    (tmp_path / "a.pdf").write_bytes(b"mismo contenido")
    (tmp_path / "b.pdf").write_bytes(b"mismo contenido")
    (tmp_path / "c.pdf").write_bytes(b"otro contenido")
    assert huella(tmp_path / "a.pdf") == huella(tmp_path / "b.pdf") != huella(tmp_path / "c.pdf") and len(huella(tmp_path / "a.pdf")) == 64


def test_marcar_dos_veces_no_duplica_y_el_error_no_cuenta_como_procesado(tmp_path):
    con = abrir_registro(tmp_path / "salidas" / "resultados.duckdb")
    marcar(con, "abc", "POL-0001.pdf", "error", "error_en_etapa:ocr")
    assert not ya_procesado(con, "abc")
    marcar(con, "abc", "POL-0001.pdf", "ok")
    marcar(con, "abc", "POL-0001.pdf", "ok")
    assert ya_procesado(con, "abc") and con.execute("SELECT count(*) FROM registro").fetchone()[0] == 1
    con.close()


def test_un_error_transitorio_se_reintenta_con_esperas_crecientes():
    esperas, llamadas = [], []

    def lectura():
        llamadas.append(1)
        if len(llamadas) < 3:
            raise PermissionError("archivo bloqueado por otro programa")
        return "leído"

    assert reintentar(lectura, intentos=3, esperas=[1, 2, 4], dormir=esperas.append) == ("leído", 3) and esperas == [1, 2]


def test_un_archivo_danado_no_se_reintenta():
    llamadas = []

    def lectura():
        llamadas.append(1)
        raise ValueError("PDF dañado")

    with pytest.raises(ValueError):
        reintentar(lectura, dormir=lambda s: None)
    assert len(llamadas) == 1


def test_si_el_bloqueo_sigue_se_agotan_las_repeticiones_y_sube_el_error():
    esperas = []

    def lectura():
        raise PermissionError("archivo bloqueado")

    with pytest.raises(PermissionError):
        reintentar(lectura, intentos=3, esperas=[1, 2, 4], dormir=esperas.append)
    assert esperas == [1, 2, 4]


def test_la_cuarentena_copia_el_archivo_y_anota_el_motivo(tmp_path):
    (tmp_path / "LOT-0007.pdf").write_bytes(b"%PDF-cifrado")
    copia = a_cuarentena(tmp_path / "LOT-0007.pdf", tmp_path / "cuarentena", "pdf_cifrado", "el PDF pide contraseña")
    linea = json.loads((tmp_path / "cuarentena" / "registro_errores.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert copia.is_file() and (tmp_path / "LOT-0007.pdf").is_file() and (linea["archivo"], linea["motivo"]) == ("LOT-0007.pdf", "pdf_cifrado")
