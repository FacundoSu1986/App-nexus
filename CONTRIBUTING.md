# Guía de Contribución

¡Gracias por tu interés en contribuir a **App-nexus**! Esta guía te ayudará a configurar tu entorno, entender las convenciones del proyecto y enviar tus cambios.

---

## 1. Cómo hacer fork y clonar el repositorio

1. Haz clic en el botón **Fork** en la esquina superior derecha de la página del repositorio en GitHub.
2. Clona tu fork localmente:

   ```bash
   git clone https://github.com/<tu-usuario>/App-nexus.git
   cd App-nexus
   ```

3. Agrega el repositorio original como *upstream* para mantener tu fork actualizado:

   ```bash
   git remote add upstream https://github.com/FacundoSu1986/App-nexus.git
   ```

4. Antes de empezar a trabajar, sincroniza tu rama `main` con *upstream*:

   ```bash
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```

---

## 2. Configuración del entorno de desarrollo

### Requisitos previos

- **Python 3.10** o superior
- **pip** (incluido con Python)
- **Git**

### Pasos

1. Crea un entorno virtual:

   ```bash
   python -m venv .venv
   ```

2. Activa el entorno virtual:

   - **Windows:**

     ```bash
     .venv\Scripts\activate
     ```

   - **Linux / macOS:**

     ```bash
     source .venv/bin/activate
     ```

3. Instala las dependencias:

   ```bash
   pip install -r requirements.txt
   ```

4. Ejecuta la aplicación para verificar que todo funciona:

   ```bash
   python main.py
   ```

5. Ejecuta los tests:

   ```bash
   python -m pytest tests/ -v
   ```

---

## 3. Guía de estilo de código

### Estilo general

- Seguimos **PEP 8** para el estilo de código Python.
- Usa **4 espacios** para la indentación (no tabuladores).
- Las líneas no deben superar los **120 caracteres**.
- Usa **comillas dobles** (`"`) para cadenas de texto.
- Nombra las variables y funciones en **snake_case** y las clases en **PascalCase**.

### Estructura del proyecto

```
src/
├── analyzer/      # Análisis de compatibilidad de mods
├── database/      # Gestión de la base de datos SQLite
├── gui/           # Interfaz gráfica (Tkinter)
├── loot/          # Integración con LOOT masterlist
├── mo2/           # Lector de perfiles de Mod Organizer 2
└── nexus/         # Cliente de la API de Nexus Mods
tests/             # Tests unitarios (pytest)
```

### Convenciones importantes

- **Hilos y GUI:** Tkinter no es *thread-safe*. Toda actualización de la interfaz desde un hilo en segundo plano debe hacerse mediante `self.after(0, callback)`.
- **API de Nexus Mods:** Usa únicamente la API REST v1 oficial. No se permite *web scraping* (el sitio está protegido por Cloudflare).
- **Claves de API:** Las claves de API deben gestionarse mediante variables de entorno. Nunca las incluyas en el código fuente.
- **Manejo de errores:** Implementa manejo robusto de errores, especialmente para límites de tasa HTTP 429 y *timeouts*.

### Tests

- Escribe tests para todo código nuevo usando **pytest**.
- Usa **responses** para simular llamadas HTTP y **pytest-mock** para *mocking* general.
- Los archivos de test deben ubicarse en `tests/` con el prefijo `test_`.
- Ejecuta los tests antes de enviar tu PR:

  ```bash
  python -m pytest tests/ -v
  ```

---

## 4. Cómo enviar un Pull Request (PR)

1. Crea una rama nueva desde `main` con un nombre descriptivo:

   ```bash
   git checkout -b feature/mi-nueva-funcionalidad
   ```

   Usa prefijos como `feature/`, `fix/`, `docs/` o `refactor/` según corresponda.

2. Realiza tus cambios y haz commits con mensajes claros y concisos:

   ```bash
   git add .
   git commit -m "Agrega validación de claves de API"
   ```

3. Asegúrate de que todos los tests pasan:

   ```bash
   python -m pytest tests/ -v
   ```

4. Sube tu rama a tu fork:

   ```bash
   git push origin feature/mi-nueva-funcionalidad
   ```

5. Abre un **Pull Request** en GitHub desde tu fork hacia la rama `main` del repositorio original.

6. En la descripción del PR, incluye:
   - **Qué** cambia tu PR.
   - **Por qué** es necesario el cambio.
   - Capturas de pantalla si hay cambios en la interfaz.
   - Referencias a issues relacionados (por ejemplo, `Closes #12`).

7. Espera la revisión de código. Es posible que te pidamos ajustes antes de fusionar el PR.

---

## 5. Buenos primeros issues para contribuir

Si es tu primera contribución, estas son algunas áreas donde puedes empezar:

- **Documentación:** Mejorar el `README.md`, agregar docstrings a funciones y clases, o traducir documentación.
- **Tests:** Aumentar la cobertura de tests existentes o agregar tests para casos límite.
- **Interfaz:** Mejorar mensajes de error en la GUI, agregar tooltips o mejorar la accesibilidad.
- **Internacionalización (i18n):** Preparar la aplicación para soportar múltiples idiomas.
- **Validación de datos:** Agregar validaciones para las respuestas de la API de Nexus Mods.
- **Logging:** Mejorar los mensajes de log para facilitar la depuración.

Busca issues etiquetados con **`good first issue`** o **`help wanted`** en la [página de issues](https://github.com/FacundoSu1986/App-nexus/issues) del repositorio.

---

¡Esperamos tu contribución! Si tienes dudas, no dudes en abrir un issue o preguntar en los comentarios de un PR existente.
