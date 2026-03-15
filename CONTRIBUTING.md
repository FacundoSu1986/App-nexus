# Guía de Contribución

¡Gracias por tu interés en contribuir a **App-nexus**! Esta guía te ayudará a comenzar.

## Cómo Contribuir

1. Hacé un fork del repositorio.
2. Creá una rama para tu cambio: `git checkout -b mi-cambio`.
3. Realizá tus cambios y asegurate de que los tests pasen.
4. Hacé commit con un mensaje descriptivo: `git commit -m "Descripción del cambio"`.
5. Pusheá tu rama: `git push origin mi-cambio`.
6. Abrí un Pull Request describiendo tus cambios.

## Configuración del Entorno

```bash
# Clonar tu fork
git clone https://github.com/<tu-usuario>/App-nexus.git
cd App-nexus

# Instalar dependencias
pip install -r requirements.txt

# Ejecutar tests
python -m pytest tests/ -v
```

## Estilo de Código

- Seguimos las convenciones de **PEP 8** para Python.
- Usá type hints cuando sea posible.
- Los docstrings deben seguir el formato NumPy/Google.
- La interfaz de usuario debe estar en **español**.

## Idioma de la Interfaz

Todas las cadenas de texto visibles para el usuario deben estar en **español**. Esto incluye:

- Etiquetas de botones y campos
- Mensajes de diálogos (advertencias, errores, información)
- Mensajes de la barra de estado
- Encabezados de columnas y pestañas
- Texto del reporte de análisis

Los comentarios en el código y los mensajes de log pueden permanecer en inglés.

## Tests

- Los tests se escriben con **pytest**.
- Ubicá los tests en la carpeta `tests/` con el prefijo `test_`.
- Ejecutá los tests antes de enviar tu PR:

```bash
python -m pytest tests/ -v
```

## Reportar Errores

Si encontrás un error, abrí un issue incluyendo:

- Descripción del problema
- Pasos para reproducirlo
- Comportamiento esperado vs. actual
- Versión de Python y sistema operativo

## Sugerencias y Mejoras

Las sugerencias son bienvenidas. Abrí un issue con la etiqueta `mejora` para proponer nuevas funcionalidades.
