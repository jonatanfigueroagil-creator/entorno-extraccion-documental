"""Pruebas de orquestacion/config.py (no necesitan Tesseract ni un modelo de lenguaje)."""
import pytest
import yaml

from mi_pipeline.orquestacion.config import RUTA_CONFIG, ErrorConfiguracion, cargar_config


def yaml_con(tmp_path, cambiar):
    """Copia del YAML del paquete con un cambio en la sección ``orquestacion``."""
    datos = yaml.safe_load(RUTA_CONFIG.read_text(encoding="utf-8"))
    cambiar(datos["orquestacion"])
    ruta = tmp_path / "pipeline.yaml"
    ruta.write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")
    return ruta


def test_el_yaml_del_paquete_es_valido():
    cfg = cargar_config()
    assert cfg.orquestacion.etapas == ["control", "ingesta", "ocr", "pln"] and cfg.orquestacion.motor_ocr == "tesseract"
    assert cfg.reintentos.espera_s == [1, 2, 4] and cfg.orquestacion.tipo_por_prefijo["POL"] == "poliza"


def test_una_clave_mal_escrita_se_rechaza_con_su_mensaje(tmp_path):
    ruta = yaml_con(tmp_path, lambda orq: orq.update(trabajdores=8))
    with pytest.raises(ErrorConfiguracion) as error:
        cargar_config(ruta)
    assert "orquestacion.trabajdores: clave desconocida" in str(error.value) and "'trabajadores'" in str(error.value)


def test_las_etapas_fuera_de_orden_se_rechazan(tmp_path):
    ruta = yaml_con(tmp_path, lambda orq: orq.update(etapas=["ocr", "ingesta"]))
    with pytest.raises(ErrorConfiguracion):
        cargar_config(ruta)


def test_las_salidas_se_llevan_a_otra_carpeta(tmp_path):
    cfg = cargar_config().en_carpeta(tmp_path)
    assert cfg.almacenamiento.duckdb == str(tmp_path / "resultados.duckdb") and cfg.cuarentena.carpeta == str(tmp_path / "cuarentena")
