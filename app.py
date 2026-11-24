"""Tablero del Data Mart PAGMAC — Práctica 4 (Bases de Datos Estructuradas).

Cómo correrlo (en tu computadora, dentro de la carpeta streamlit_app):
    python -m pip install -r requirements.txt
    python -m streamlit run app.py

Se abre en el navegador en http://localhost:8501. La contraseña de MySQL
se escribe en el menú lateral, nunca queda guardada en el código.
"""

import os
from urllib.parse import quote_plus

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

import datos as D

st.set_page_config(page_title="Data Mart PAGMAC — Tablero", layout="wide")

st.title("📊 Tablero del Data Mart PAGMAC")
st.caption("Práctica 4 · Bases de Datos Estructuradas 2027-1 · Fuente: PAGMAC")

# ------------------------------------------------------------ fuente de datos
st.sidebar.header("Datos")
demo_por_defecto = os.environ.get("PAGMAC_DEMO") == "1"
fuente = st.sidebar.radio(
    "Fuente de datos",
    ["Mi base de datos (MySQL)", "Datos de ejemplo (demo)"],
    index=1 if demo_por_defecto else 0,
)

dfs = None
if fuente.startswith("Datos de ejemplo"):
    dfs = D.datos_demo()
    st.sidebar.success("Usando datos de ejemplo (sintéticos).")
else:
    st.sidebar.subheader("Conexión a MySQL")
    host = st.sidebar.text_input("Host", value="localhost")
    puerto = st.sidebar.text_input("Puerto", value="3306")
    usuario = st.sidebar.text_input("Usuario", value="root")
    password = st.sidebar.text_input("Contraseña", value="", type="password")
    base = st.sidebar.text_input("Base de datos", value="data_mart_pagmac")

    @st.cache_resource(show_spinner=False)
    def _engine(host, puerto, usuario, password, base):
        url = (f"mysql+pymysql://{usuario}:{quote_plus(password)}"
               f"@{host}:{puerto}/{base}")
        return create_engine(url)

    # OJO: antes _cargar recibía el engine como parámetro "_eng", y los
    # parámetros con "_" NO entran en la clave de caché. Si la primera carga
    # falló (base vacía o mal escrita), el resultado vacío quedaba guardado
    # y se seguía mostrando aunque después se corrigiera la base. Ahora la
    # clave de caché son los datos de conexión, así que al corregirlos se
    # vuelve a cargar de verdad.
    @st.cache_data(show_spinner="Cargando tablas del data mart…")
    def _cargar(host, puerto, usuario, password, base):
        return D.cargar_desde_mysql(_engine(host, puerto, usuario, password, base))

    if st.sidebar.button("Conectar y cargar"):
        st.cache_data.clear()
    try:
        eng = _engine(host, puerto, usuario, password, base)
        # Diagnóstico: ¿a qué base nos conectamos realmente y qué tablas hay?
        with eng.connect() as conn:
            db_actual = conn.execute(text("SELECT DATABASE()")).scalar()
            tablas_en_base = [r[0] for r in conn.execute(text("SHOW TABLES"))]
        st.sidebar.write(f"Base conectada: {db_actual or '(ninguna)'}")
        if db_actual != base:
            st.sidebar.warning(
                f"La base conectada ({db_actual}) no es la del campo "
                f"({base}). Revisa el campo «Base de datos».")
        st.sidebar.write(f"Tablas en esa base: {len(tablas_en_base)}")
        dfs = _cargar(host, puerto, usuario, password, base)
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo conectar a MySQL: {e}")
        st.info("Revisa que MySQL esté corriendo, el usuario y la contraseña. "
                "O cambia arriba a «Datos de ejemplo (demo)» para ver el tablero.")
        st.stop()

if dfs is None:
    st.stop()

# Las tablas deben ser las del notebook corregido; si son las del notebook
# viejo (o de otra base), las columnas no coinciden y el tablero no puede
# graficar. Se avisa claro en vez de tronar con un KeyError.
problemas = D.validar(dfs)
if problemas:
    st.error("Las tablas en MySQL no son las del notebook corregido:")
    for p in problemas:
        st.write("• " + p)
    st.info("Lo más probable es que tu base tenga las tablas del notebook viejo. "
            "Haz DROP DATABASE data_mart_pagmac, corre completo el notebook "
            "corregido (procedimiento_etl_corregido.ipynb) y vuelve a pegar el "
            "script de PK/FK. Para ver qué tiene tu tabla, en Workbench corre: "
            "DESCRIBE dim_alumno;")
    st.stop()

st.sidebar.success(
    f"Cargado: {len(dfs['fct_cal_alumno']):,} evaluaciones, "
    f"{len(dfs['dim_alumno']):,} alumnos, "
    f"{len(dfs['dim_asignatura']):,} materias.")

d = D.preparar(dfs)
cal, ext, insc = d["cal"], d["ext"], d["insc"]

# ------------------------------------------------------------------- filtros
st.sidebar.header("Filtros")
periodos = st.sidebar.multiselect(
    "Periodo UNAM", options=d["orden_periodos"], default=d["orden_periodos"])
generaciones = st.sidebar.multiselect(
    "Generación", options=sorted(d["dim_alumno"]["generacion"].dropna().unique()),
    default=sorted(d["dim_alumno"]["generacion"].dropna().unique()))
sexos = st.sidebar.multiselect(
    "Sexo", options=["Hombre", "Mujer"], default=["Hombre", "Mujer"])
tipos = st.sidebar.multiselect(
    "Tipo de evaluación", options=["O", "E"], default=["O", "E"])

cal_f = D.filtrar_cal(cal, periodos, generaciones, sexos, tipos)
ext_f = ext[ext["periodo_unam"].isin(periodos)] if periodos else ext
d_f = {"cal": cal_f, "ext": ext_f, "insc": insc,
       "dim_alumno": d["dim_alumno"], "dim_asignatura": d["dim_asignatura"],
       "dim_tiempo": d["dim_tiempo"], "dim_votacion": d["dim_votacion"],
       "orden_periodos": d["orden_periodos"]}

st.sidebar.header("Secciones")
pagina = st.sidebar.radio(
    "Ver", ["Resumen", "Alumnos por periodo", "Calificaciones", "Materias",
            "Generaciones", "Extras largos", "Inscripciones y optativas",
            "Buscar alumno"],
    label_visibility="collapsed")


def descargar(df, nombre):
    st.download_button(f"⬇️ Descargar {nombre} (CSV)",
                       df.to_csv(index=False).encode("utf-8"),
                       file_name=f"{nombre}.csv", mime="text/csv")


# ------------------------------------------------------------------- páginas
if pagina == "Resumen":
    k = D.kpis(d_f)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alumnos (con calificación)", f"{k['alumnos']:,}")
    c2.metric("Evaluaciones", f"{k['evaluaciones']:,}")
    c3.metric("Promedio global", f"{k['promedio']:.2f}" if pd.notna(k["promedio"]) else "—")
    c4.metric("Índice de reprobación", f"{k['ind_reprobacion']:.1f}%")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Aprobadas", f"{k['aprobados']:,}")
    c2.metric("Reprobadas (incl. NA)", f"{k['reprobados']:,}")
    c3.metric("NP (no se presentó)", f"{k['np']:,}")
    c4.metric("NA (no aprobó)", f"{k['na']:,}")
    st.plotly_chart(D.fig_estado_periodo(cal_f), width="stretch")
    st.plotly_chart(D.fig_alumnos_periodo(cal_f), width="stretch")
    st.caption("Nota: «alumnos activos por periodo» = alumnos con calificación "
               "registrada en ese periodo. La tabla materiainscrita no trae "
               "periodo, así que no hay inscritos por fecha exacta.")

elif pagina == "Alumnos por periodo":
    st.plotly_chart(D.fig_alumnos_periodo(cal_f), width="stretch")
    tabla = (cal_f.groupby("periodo_label", observed=True)
             .agg(alumnos=("id_dim_estudiante", "nunique"),
                  evaluaciones=("id_hecho", "size"))
             .reset_index().rename(columns={"periodo_label": "Periodo UNAM"}))
    st.dataframe(tabla, width="stretch")
    descargar(tabla, "alumnos_por_periodo")

elif pagina == "Calificaciones":
    st.plotly_chart(D.fig_distribucion_calif(cal_f), width="stretch")
    st.plotly_chart(D.fig_estado_periodo(cal_f), width="stretch")
    tabla = (cal_f.groupby("estado_evaluacion").size()
             .reset_index(name="evaluaciones"))
    st.dataframe(tabla, width="stretch")

elif pagina == "Materias":
    st.plotly_chart(D.fig_reprobacion_materia(cal_f), width="stretch")
    st.plotly_chart(D.fig_promedio_materia(cal_f), width="stretch")
    st.plotly_chart(D.fig_promedio_materia(cal_f, peores=True),
                    width="stretch")
    tabla = (cal_f.groupby(["clave", "nombre"], observed=True)
             .agg(evaluaciones=("id_hecho", "size"),
                  promedio=("calificacion_num", "mean"),
                  aprobadas=("es_aprobatoria", "sum"),
                  reprobadas=("es_reprobada", "sum"),
                  np=("es_np", "sum"), na=("es_na", "sum"))
             .reset_index())
    ev = tabla[tabla["evaluaciones"] - tabla["np"] > 0]
    tabla["ind_reprobacion"] = (tabla["reprobadas"]
                                / (tabla["evaluaciones"] - tabla["np"]) * 100)
    st.dataframe(tabla.sort_values("ind_reprobacion", ascending=False),
                 width="stretch")
    descargar(tabla, "metricas_por_materia")

elif pagina == "Generaciones":
    st.plotly_chart(D.fig_alumnos_generacion(d["dim_alumno"]),
                    width="stretch")
    st.plotly_chart(D.fig_promedio_generacion(cal_f), width="stretch")
    st.plotly_chart(D.fig_reprobacion_generacion(cal_f), width="stretch")
    tabla = (cal_f.groupby("generacion", observed=True)
             .agg(alumnos=("id_dim_estudiante", "nunique"),
                  evaluaciones=("id_hecho", "size"),
                  promedio=("calificacion_num", "mean"),
                  reprobadas=("es_reprobada", "sum"))
             .reset_index())
    st.dataframe(tabla, width="stretch")
    descargar(tabla, "metricas_por_generacion")

elif pagina == "Extras largos":
    k = D.kpis(d_f)
    st.metric("Votos de extra largo (con filtros de periodo)", f"{k['extras']:,}")
    st.plotly_chart(D.fig_extras_materia(ext_f), width="stretch")
    st.plotly_chart(D.fig_extras_periodo(ext_f), width="stretch")
    tabla = (ext_f.groupby(["clave", "nombre"], observed=True)
             .agg(extras=("cantidad", "sum"),
                  alumnos=("id_dim_estudiante", "nunique"))
             .reset_index().sort_values("extras", ascending=False))
    st.dataframe(tabla, width="stretch")
    descargar(tabla, "extras_por_materia")

elif pagina == "Inscripciones y optativas":
    st.plotly_chart(D.fig_inscritos_materia(insc), width="stretch")
    st.plotly_chart(D.fig_optativas(insc), width="stretch")
    st.plotly_chart(D.fig_sexo(d["dim_alumno"]), width="stretch")
    tabla = (insc.groupby(["clave", "nombre", "opt_ob"], observed=True)
             .agg(inscripciones=("cantidad", "sum"),
                  alumnos=("id_dim_estudiante", "nunique"))
             .reset_index().sort_values("inscripciones", ascending=False))
    st.dataframe(tabla, width="stretch")
    descargar(tabla, "inscripciones_por_materia")
    st.caption("Inscripciones totales por materia (sin periodo: la fuente "
               "materiainscrita no registra en qué periodo se inscribió).")

elif pagina == "Buscar alumno":
    cuenta = st.text_input("Número de cuenta (username)", "")
    if cuenta:
        alum = d["dim_alumno"][d["dim_alumno"]["username"].astype(str) == cuenta.strip()]
        if len(alum) == 0:
            alum = d["dim_alumno"][
                d["dim_alumno"]["nombre_completo"].str.contains(cuenta, case=False, na=False)]
        if len(alum) == 0:
            st.warning("No encontré a ese alumno en dim_alumno.")
        else:
            a = alum.iloc[0]
            st.subheader(f"{a['nombre_completo']} · {a['username']}")
            st.write(f"Generación: {a['generacion']} · Sexo: {a['sexo']}")
            hist = cal[cal["id_dim_estudiante"] == a["id_estudiante"]].copy()
            if len(hist) == 0:
                st.info("Este alumno no tiene calificaciones en el hecho.")
            else:
                c1, c2, c3 = st.columns(3)
                c1.metric("Evaluaciones", len(hist))
                c2.metric("Promedio", f"{hist['calificacion_num'].mean():.2f}")
                c3.metric("Reprobadas", int(hist["es_reprobada"].sum()))
                tabla = (hist[["periodo_label", "clave", "nombre",
                               "calificacion_original", "calificacion_num",
                               "estado_evaluacion", "tipo_evaluacion",
                               "total_intentos"]]
                         .sort_values(["periodo_label", "clave"])
                         .rename(columns={"periodo_label": "Periodo UNAM"}))
                st.dataframe(tabla, width="stretch")
                descargar(tabla, f"historial_{a['username']}")
