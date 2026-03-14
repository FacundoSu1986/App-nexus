# App-nexus — Skyrim Mod Compatibility Manager

Una aplicación Windows para gestionar la compatibilidad de mods de Skyrim usando datos de **Nexus Mods** y **Mod Organizer 2**.

---

## ¿Qué hace esta aplicación?

| Funcionalidad | Descripción |
|---|---|
| 📥 **Lee tu lista de mods de MO2** | Importa `modlist.txt` y `plugins.txt` desde cualquier perfil de Mod Organizer 2 |
| 🔍 **Scrapea Nexus Mods** | Descarga descripciones, requisitos, parches de compatibilidad y reportes de bugs/posts vía la API oficial y web scraping |
| 🗄️ **Base de datos local** | Guarda toda la información en SQLite local — funciona sin internet después del primer sync |
| ⚠️ **Análisis de compatibilidad** | Detecta mods faltantes, parches necesarios, conflictos conocidos y violaciones en el orden de carga |
| 📋 **Reporte detallado** | Muestra exactamente qué falta, qué conflicta y cómo debería estar el load order |

---

## Arquitectura

```
App-nexus/
├── main.py                        # Punto de entrada
├── requirements.txt
├── build/
│   └── app_nexus.spec             # Configuración PyInstaller (.exe)
├── src/
│   ├── nexus/
│   │   ├── api.py                 # Wrapper API REST de Nexus Mods v1
│   │   └── scraper.py             # Web scraper (requisitos, bugs, incompatibilidades)
│   ├── mo2/
│   │   └── reader.py              # Lector de modlist.txt / plugins.txt de MO2
│   ├── database/
│   │   └── manager.py             # Base de datos SQLite local (cache)
│   ├── analyzer/
│   │   └── compatibility.py       # Motor de análisis de compatibilidad
│   └── gui/
│       ├── main_window.py         # Ventana principal (tkinter)
│       └── mod_detail_frame.py    # Panel de detalle de mod (tabs)
└── tests/
    ├── test_database.py
    ├── test_mo2_reader.py
    ├── test_compatibility.py
    ├── test_nexus_api.py
    └── test_nexus_scraper.py
```

### Flujo de datos

```
MO2 modlist.txt ──► MO2Reader ──► MO2Profile (lista de mods habilitados)
                                        │
                                        ▼
Nexus Mods API  ──► NexusAPI   ──► DatabaseManager (SQLite cache)
Nexus Web Pages ──► NexusScraper       │
                                        ▼
                               CompatibilityAnalyzer
                                        │
                                        ▼
                                   Reporte final
                            (faltantes / conflictos / load order)
```

---

## Instalación y uso

### Requisitos

- Python 3.10 o superior
- Windows 10/11 (también funciona en Linux/macOS para desarrollo)

### Instalar dependencias

```bash
pip install -r requirements.txt
```

### Ejecutar directamente con Python

```bash
python main.py
```

### Compilar a .exe (Windows)

```bash
pip install pyinstaller
pyinstaller build/app_nexus.spec
# El ejecutable queda en dist/AppNexus.exe
```

---

## Configuración inicial

### 1. Obtener una API Key de Nexus Mods (gratis)

1. Crea una cuenta en [nexusmods.com](https://www.nexusmods.com) (gratis)
2. Ve a **Mi cuenta → API Keys** o entra a:
   `https://www.nexusmods.com/users/myaccount?tab=api`
3. Genera una **Personal API Key**
4. Pégala en el campo "Nexus API Key" de la aplicación

> **Límites de la cuenta gratuita:** 100 solicitudes por día. Suficiente para sincronizar ~50 mods por día (la app cachea los resultados para no repetir solicitudes).

### 2. Cargar tu lista de mods de MO2

1. En MO2, ve a tu perfil activo
2. El archivo `modlist.txt` se encuentra en:
   ```
   %LOCALAPPDATA%\ModOrganizer\<instancia>\profiles\<perfil>\modlist.txt
   ```
   Ejemplo: `C:\Users\TuNombre\AppData\Local\ModOrganizer\Skyrim SE\profiles\Default\modlist.txt`
3. En la aplicación, haz clic en **Browse…** y selecciona ese archivo
4. Haz clic en **Load Mod List**

### 3. Sincronizar datos de Nexus

Haz clic en **🔄 Sync from Nexus** — la aplicación consultará la API y el sitio web de Nexus Mods para obtener:
- Descripción completa del mod
- Lista de requisitos (pestaña "Requirements" de cada mod)
- Reportes de usuarios (pestaña "Bugs" / "Posts")
- Menciones de incompatibilidades en la descripción

Los datos se guardan en SQLite en:
```
%APPDATA%\AppNexus\app_nexus.db
```

### 4. Analizar

Haz clic en **🔍 Analyse** para ver el reporte completo.

---

## ¿Necesito contratar un servidor?

**Respuesta corta: No, para uso personal.**

Esta aplicación usa una **base de datos SQLite local** que se guarda en tu propia máquina. No necesitas ningún servidor.

| Escenario | ¿Necesito servidor? | Solución |
|---|---|---|
| Uso personal (un solo usuario) | ❌ No | SQLite local en `%APPDATA%\AppNexus\` |
| Compartir la base de datos con amigos (pequeña comunidad) | ⚠️ Opcional | Se puede copiar el archivo `.db` o usar un servidor NAS/compartido en red local |
| Aplicación pública con miles de usuarios simultáneos | ✅ Sí | Migrar a PostgreSQL en un VPS (~$5–$10/mes en DigitalOcean, Hetzner, etc.) |

Para que varios usuarios compartan una base de datos centralizada, necesitarías:
1. Un **VPS** (Virtual Private Server) con una base de datos PostgreSQL/MySQL
2. Un **backend REST API** (ej. FastAPI en Python) que exponga los datos
3. Modificar el cliente `.exe` para consultar ese servidor en vez del SQLite local

Para empezar, el SQLite local es más que suficiente.

---

## Datos que se almacenan

### Tabla `mods`
- Nombre, descripción completa, resumen, versión, autor
- URL de la página en Nexus Mods
- Fecha del último scraping

### Tabla `requirements`
- Mods requeridos por cada mod (dependencias duras)
- Parches de compatibilidad recomendados
- URL para descargar cada requisito

### Tabla `incompatibilities`
- Mods que NO deben usarse juntos
- Razón del conflicto (extraída de la descripción)

### Tabla `issues`
- Reportes de bugs y posts de usuarios (título, cuerpo, autor, fecha)

### Tabla `load_order_rules`
- Reglas de orden de carga (`AFTER` / `BEFORE`)

---

## Reporte de análisis — ejemplo

```
╔══════════════════════════════════════════════════════════╗
  Mods analizados : 147 habilitados / 152 totales
  Mods faltantes  : 3  (parches: 2)
  Incompatibles   : 1
  Orden de carga ⚠: 2
╚══════════════════════════════════════════════════════════╝

── REQUISITOS FALTANTES ──
  [REQUIRED] 'SKSE64' requerido por 'SkyUI'
    → https://www.nexusmods.com/skyrimspecialedition/mods/30379
  [PATCH]    'SkyUI - Survival Mode Patch' requerido por 'SkyUI'
    → https://www.nexusmods.com/skyrimspecialedition/mods/17884

── INCOMPATIBILIDADES ──
  ⚠ 'Immersive Citizens' conflicta con 'Interesting NPCs'
    Razón: Overwrites AI packages for the same NPCs

── VIOLACIONES DE ORDEN DE CARGA ──
  'SkyUI.esp' debería cargarse AFTER 'USSEP.esp'
  (actual: #12, objetivo: #15)
```

---

## Ejecutar los tests

```bash
python -m pytest tests/ -v
```

65 tests, todos pasan ✅

---

## Licencia

MIT
