# C-IMPL-01 — instalación y verificación en Ubuntu 24.04 + XFCE + PyCharm

**Objetivo:** desplegar este scaffold en la VM; **no** ejecutar R0–R7 todavía. No se incluyen fuentes privadas ni cambios científicos.

## A. Descomprimir y abrir el repositorio

Copia el ZIP a tu VM, descomprímelo desde el directorio donde quieras guardar proyectos y entra en el directorio raíz `simfleet-edg`. Ejemplo:

```bash
mkdir -p "$HOME/projects/simfleet-edg-bootstrap"
cd "$HOME/projects/simfleet-edg-bootstrap"
unzip "$HOME/Descargas/SimFleet_EDG_C_IMPL_01_Repository_Scaffold_v1.zip"
cd SimFleet_EDG_C_IMPL_01_Repository_Scaffold_v1/simfleet-edg
pwd
```

> Ajusta solo la ruta del ZIP a donde lo hayas copiado. No copies MiD/Zensus/LOR al repositorio todavía.

## B. Dependencias del sistema e intérprete

```bash
sudo apt update
sudo apt install -y git unzip python3.12 python3.12-venv python3-pip
python3.12 --version
git --version
```

Si `python3.12 -m venv` informa de que falta `ensurepip`, revisa que esté instalado `python3.12-venv`.

## C. Inicializar Git (sin remoto todavía)

```bash
git init -b main
git status
```

No es necesario GitHub para este paso. No configures `user.name` ni `user.email` con valores inventados; si `git commit` lo solicita, configura tu identidad real o la identidad de investigación que uses habitualmente.

## D. Crear `.venv` para PyCharm

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install -e '.[dev]'
```

En PyCharm, abre **esta carpeta `simfleet-edg`** (no la carpeta ZIP padre) y selecciona el intérprete existente:

```text
<tu-ruta>/simfleet-edg/.venv/bin/python
```

Los extras científicos `[reproduction]` y Jupyter `[notebooks]` se instalarán durante C-IMPL-02/C-IMPL-04, cuando fijemos el entorno y el kernel.

## E. Verificaciones antes del commit

```bash
python -m simfleet_edg --version
python -m pytest -q
python -m ruff check .
python scripts/verify_scaffold.py
git status --short
git check-ignore .venv/lib/placeholder.py data/raw/placeholder.csv artifacts/runs/example.parquet
```

`git check-ignore` debe listar las rutas de ejemplo ignoradas aunque esos archivos no existan. Los checks del script solo dan PASS una vez que existe `.git` y el intérprete es 3.12.

## F. Primer commit

```bash
git add .
git status --short
git commit -m 'chore: bootstrap PRE-F3 reproducibility repository'
git status --short
git rev-parse HEAD
```

**No subas nunca** datos MiD/Zensus/LOR ni snapshots sin revisar permisos de difusión. `git status --short` debería estar vacío tras el commit.

## G. Evidencia para volver a este hilo

Comparte **solo la salida textual** de:

```bash
python3.12 --version
python -m simfleet_edg --version
python -m pytest -q
python -m ruff check .
python scripts/verify_scaffold.py
git status --short
git rev-parse HEAD
```

Así podremos registrar `C-IMPL-01 = VERIFIED_IN_VM` sin confundirlo con `R0 = SUPERADO`.

## H. Si no hay Internet en la VM

La instalación de dependencias de desarrollo podría fallar. No cambies el framework ni elimines pruebas para sortearlo: registra el fallo e indica si tienes un mirror/wheelhouse local; resolveremos esa dependencia antes de cerrar C-IMPL-01.
