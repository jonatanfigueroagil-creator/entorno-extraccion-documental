"""Pruebas de la rueda (S07): el paquete se construye con pip wheel y lleva lo necesario para instalarse en otra máquina."""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

import mi_pipeline

PAQUETE = Path(mi_pipeline.__file__).resolve().parent
DECLARADAS = ("pandas", "duckdb", "pyyaml")   # dependencias que la rueda debe declarar (en minúsculas)


@pytest.fixture(scope="module")
def rueda(tmp_path_factory):
    """Construye la rueda desde una copia del paquete (así la carpeta del repositorio queda limpia)."""
    base = tmp_path_factory.mktemp("rueda")
    fuente = base / "fuente"
    fuente.mkdir()
    shutil.copy2(PAQUETE.parent / "pyproject.toml", fuente / "pyproject.toml")
    shutil.copytree(PAQUETE, fuente / PAQUETE.name, ignore=shutil.ignore_patterns("__pycache__", "_respaldo_*", "golden"))
    corrida = subprocess.run([sys.executable, "-m", "pip", "wheel", str(fuente), "--no-deps", "--no-build-isolation", "-w", str(base / "dist")],
                             capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    assert corrida.returncode == 0, "pip wheel falló:\n" + corrida.stderr[-800:]
    return next((base / "dist").glob("*.whl"))


def test_la_rueda_se_construye_con_el_nombre_y_la_version_del_paquete(rueda):
    assert mi_pipeline.__version__ == "0.7.0"
    assert rueda.name == f"{PAQUETE.name}-0.7.0-py3-none-any.whl"


def test_la_rueda_lleva_el_codigo_y_la_configuracion_pero_no_las_pruebas(rueda):
    with zipfile.ZipFile(rueda) as z:
        nombres = z.namelist()
    assert f"{PAQUETE.name}/__main__.py" in nombres and f"{PAQUETE.name}/config/pipeline.yaml" in nombres
    assert not any("/tests/" in nombre for nombre in nombres), "las pruebas no viajan en la rueda"


def test_la_rueda_declara_sus_dependencias(rueda):
    with zipfile.ZipFile(rueda) as z:
        metadatos = z.read(next(n for n in z.namelist() if n.endswith(".dist-info/METADATA"))).decode("utf-8").lower()
    faltan = [paquete for paquete in DECLARADAS if f"requires-dist: {paquete}" not in metadatos]
    assert not faltan, f"La rueda no declara: {faltan}. Lo que no está escrito en el paquete no viaja."
