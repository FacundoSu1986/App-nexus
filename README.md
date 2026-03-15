# App-nexus

**Gestor de Compatibilidad de Mods de Skyrim**

App-nexus es una herramienta de escritorio que ayuda a los jugadores de Skyrim a gestionar la compatibilidad de sus mods. Se integra con [Nexus Mods](https://www.nexusmods.com/) y [Mod Organizer 2](https://www.modorganizer.org/) para detectar requisitos faltantes, conflictos e incompatibilidades.

## Características

- **Validación de clave API de Nexus Mods** — autenticación segura con la API de Nexus.
- **Carga de perfiles MO2** — lee tu `modlist.txt` y `plugins.txt` directamente.
- **Sincronización con Nexus** — descarga metadatos y requisitos de cada mod.
- **Análisis de compatibilidad** — detecta mods requeridos faltantes y parches.
- **Integración con LOOT** — identifica incompatibilidades y advertencias del masterlist de LOOT.
- **Interfaz en español** — toda la interfaz está traducida al español.

## Requisitos Previos

- Python 3.10 o superior
- Tkinter (incluido en la mayoría de distribuciones de Python)

## Instalación

```bash
# Clonar el repositorio
git clone https://github.com/FacundoSu1986/App-nexus.git
cd App-nexus

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

```bash
python main.py
```

1. Ingresá tu clave API de Nexus Mods y hacé clic en **Validar Clave**.
2. Seleccioná tu archivo `modlist.txt` de MO2 usando **Explorar…** y hacé clic en **Cargar Mods**.
3. Hacé clic en **Sincronizar Nexus** para descargar los datos de cada mod.
4. Hacé clic en **Analizar** para ver el reporte de compatibilidad.
5. Opcionalmente, hacé clic en **Actualizar LOOT** para descargar el masterlist de LOOT.

## Estructura del Proyecto

```
App-nexus/
├── main.py                  # Punto de entrada de la aplicación
├── src/
│   ├── analyzer/            # Motor de análisis de compatibilidad
│   ├── database/            # Gestor de base de datos SQLite
│   ├── gui/                 # Interfaz gráfica (Tkinter)
│   ├── loot/                # Parser del masterlist de LOOT
│   ├── mo2/                 # Lector de perfiles de Mod Organizer 2
│   └── nexus/               # Cliente de la API de Nexus Mods
├── tests/                   # Tests unitarios (pytest)
├── build/                   # Configuración de PyInstaller
└── requirements.txt         # Dependencias de Python
```

## Tests

```bash
python -m pytest tests/ -v
```

## Build

Para crear un ejecutable independiente:

```bash
pyinstaller build/app_nexus.spec
```

## Licencia

Los datos del masterlist de LOOT se proporcionan bajo licencia [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/) por [loot.github.io](https://loot.github.io/).
