# Tablero del Data Mart PAGMAC — Práctica 4

Visualizaciones con menús sobre el data mart `data_mart_pagmac`
(Bases de Datos Estructuradas 2027-1, fuente PAGMAC).

## Archivos

- `app.py` — la aplicación Streamlit (el tablero).
- `datos.py` — carga de MySQL o datos de ejemplo, agregaciones y gráficas.
- `requirements.txt` — librerías necesarias.

## Cómo correrlo

En tu computadora, dentro de esta carpeta:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Se abre solo en el navegador en http://localhost:8501. Para detenerlo,
`Ctrl+C` en la terminal.

## Uso

1. En el menú lateral elige la fuente:
   - **Mi base de datos (MySQL)**: escribe host, usuario y **contraseña**
     (nunca queda guardada en el código) y pulsa «Conectar y cargar».
     Lee directo de `data_mart_pagmac`, así que primero debe estar cargada
     con el notebook corregido (`procedimiento_etl_corregido.ipynb`).
   - **Datos de ejemplo (demo)**: datos sintéticos con el mismo esquema,
     para ver el tablero sin conectarse a MySQL.
2. Filtra por periodo, generación, sexo y tipo de evaluación (O/E).
   Los filtros aplican a las páginas de calificaciones.
3. Cambia de sección en el menú lateral: Resumen, Alumnos por periodo,
   Calificaciones, Materias, Generaciones, Extras largos, Inscripciones
   y optativas, Buscar alumno.
4. Cada tabla tiene botón para descargar su CSV.

## Qué se puede reportar

- Alumnos activos por periodo (con calificación registrada).
- Aprobadas, reprobadas, NP y NA por periodo y por materia.
- Promedio global, por materia y por generación.
- Índice de reprobación y de aprovechamiento por materia y generación.
- Distribución de calificaciones (5–10, MB/B/S, NP, NA).
- Extras largos por materia y por periodo de votación.
- Inscripciones por materia; optativas más y menos elegidas.
- Alumnos por sexo y por generación; historial por número de cuenta.

## Advertencias honestas del modelo

- **Inscritos por fecha exacta no existe**: `materiainscrita` no trae
  periodo. El tablero reporta «alumnos activos por periodo» (con
  calificación registrada) e inscripciones totales por materia, y lo
  etiqueta así en cada página.
- El periodo especial `01012` (extraordinarios sin periodo capturado)
  aparece como periodo propio, no mezclado con ningún semestre.
- NA cuenta como reprobada (así quedó confirmado): entra en el índice
  de reprobación pero no en los promedios. NP no afecta promedios ni
  índices.
# Tarea_BD
