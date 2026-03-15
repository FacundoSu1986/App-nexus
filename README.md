# App-nexus — Skyrim Mod Compatibility Manager

**App-nexus** es un gestor de compatibilidad de mods para **Skyrim Special Edition**.
...descripción...

> 💡 *Proyecto hobby creado por un apasionado de Skyrim con ayuda de IAs 
> (Claude, GitHub Copilot, Gemini, Kimi). ¡Contribuciones bienvenidas!*

---


**App-nexus** es un gestor de compatibilidad de mods para **Skyrim Special Edition**.
Lee tu lista de mods de **Mod Organizer 2**, consulta la API de **Nexus Mods** y cruza los
datos con la **masterlist de LOOT** para detectar dependencias faltantes,
incompatibilidades y advertencias — todo desde una interfaz gráfica sencilla con tema oscuro.

---

## Captura de pantalla

> ![Captura de pantalla de App-nexus](docs/screenshot.png)
>
> *(Reemplaza esta imagen con una captura real de la aplicación)*

---

## Características

- **Lectura automática de Mod Organizer 2**: detecta instancias, perfiles, `modlist.txt`,
  `plugins.txt` y `meta.ini` de cada mod.
- **Consulta a la API de Nexus Mods**: obtiene nombre, descripción, requisitos y parches
  de cada mod directamente desde Nexus.
- **Análisis de compatibilidad en tres capas**:
  - Requisitos faltantes (mods necesarios que no están instalados).
  - Incompatibilidades detectadas por LOOT.
  - Advertencias y mensajes de LOOT para plugins individuales.
- **Coincidencia difusa de nombres** (umbral del 82 %) para emparejar mods aunque varíen
  en sufijo de versión o extensión de plugin (`.esp` / `.esm` / `.esl`).
- **Caché local SQLite** para no repetir consultas a la API innecesariamente.
- **Panel de detalle con pestañas**: Resumen, Descripción (con limpieza de BBCode) y
  Requisitos en tabla.
- **Informe de compatibilidad**: resumen estadístico con totales de mods, mods habilitados,
  requisitos faltantes e incompatibilidades.
- **Botón "Abrir en Nexus Mods"** para ir directo a la página de cada mod.
- **Tema oscuro** gracias a [sv-ttk](https://github.com/rdbende/Sun-Valley-ttk-theme).

---

## Instalación

### Opción A — Ejecutable para Windows

1. Ve a la sección [Releases](../../releases) de este repositorio.
2. Descarga el archivo `AppNexus.exe`.
3. Ejecuta `AppNexus.exe` — no requiere instalar Python ni dependencias.

### Opción B — Desde el código fuente

Requiere **Python 3.10+**.

```bash
# 1. Clona el repositorio
git clone https://github.com/FacundoSu1986/App-nexus.git
cd App-nexus

# 2. Instala las dependencias
pip install -r requirements.txt

# 3. Ejecuta la aplicación
python main.py
```

> **Compilar el ejecutable (opcional):**
>
> ```bash
> pyinstaller build/app_nexus.spec
> ```
>
> El archivo resultante se genera en `dist/AppNexus.exe`.

---

## Uso paso a paso

1. **Obtén tu API Key de Nexus Mods** (ver sección siguiente).
2. **Abre App-nexus** (`AppNexus.exe` o `python main.py`).
3. **Ingresa tu API Key** en el campo correspondiente de la barra de herramientas.
4. **Selecciona la carpeta de Mod Organizer 2** con el botón de ruta de MO2.
5. **Elige el perfil** de MO2 que deseas analizar.
6. **Presiona "Sincronizar"** para que la aplicación:
   - Lea la lista de mods y el orden de plugins de MO2.
   - Consulte la API de Nexus Mods para cada mod.
   - Descargue y procese la masterlist de LOOT.
   - Analice compatibilidad y genere el informe.
7. **Revisa los resultados**:
   - En el panel izquierdo, navega la lista de mods.
   - En el panel derecho, explora las pestañas *Resumen*, *Descripción* y *Requisitos*.
   - En el panel inferior, consulta el informe de compatibilidad con las dependencias
     faltantes, incompatibilidades y advertencias.

---

## Cómo obtener tu API Key de Nexus Mods

1. Inicia sesión en [nexusmods.com](https://www.nexusmods.com/).
2. Ve a **Mi cuenta → Pestaña API**:
   <https://www.nexusmods.com/users/myaccount?tab=api>
3. En la sección **Personal API Key**, haz clic en **"Request an API Key"**.
4. Copia la clave generada y pégala en App-nexus.

> La clave personal es gratuita y permite **100 solicitudes por día**.

---

## Créditos

- **Datos de masterlist**: proporcionados por el proyecto
  [LOOT](https://loot.github.io/) bajo licencia
  [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).
- **Tema visual**: [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme)
  por rdbende.

---

## Licencia

Este proyecto se distribuye bajo la licencia **MIT**. Consulta el archivo [LICENSE](LICENSE)
para más detalles.
