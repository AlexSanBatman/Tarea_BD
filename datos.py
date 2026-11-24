"""Lógica de datos del tablero PAGMAC (sin Streamlit aquí dentro).

Lee las tablas del data mart (MySQL) o genera datos de ejemplo con el
mismo esquema, y construye las agregaciones y gráficas (Plotly).

Esquema que usa (el del notebook corregido):
- dim_alumno: id_estudiante, id_auth_user, username (nº de cuenta),
  nombre_completo, email, generacion, sexo ("Hombre"/"Mujer"),
  deleg_muni, fecha_nac
- dim_asignatura: id_asignatura, clave, nombre, plan, semestre_plan,
  semestre_desc, opt_ob ("OB"/"OP"), es_optativa
- dim_tiempo: id_periodo, periodo_unam, anio_ciclo, semestre_ciclo,
  descripcion, es_periodo_estandar
- dim_votacion: id_votacion, periodo_unam, inicio, fin
- fct_cal_alumno: id_hecho, id_dim_estudiante, id_dim_asignatura,
  id_dim_periodo, calificacion_original, calificacion_num,
  es_aprobatoria, es_reprobada, es_np, es_na, estado_evaluacion
  ("APROBADA"/"REPROBADA"/"NP"), acreditado, tipo_evaluacion ("O"/"E"),
  total_intentos
- fct_extra_largo: id_hecho, id_dim_estudiante, id_dim_asignatura,
  id_dim_periodo, id_dim_votacion, fecha_voto, cantidad
- fct_inscripcion: id_hecho, id_dim_estudiante, id_dim_asignatura, cantidad
"""

import numpy as np
import pandas as pd
import plotly.express as px

TABLAS = [
    "dim_alumno", "dim_asignatura", "dim_tiempo", "dim_votacion",
    "fct_cal_alumno", "fct_extra_largo", "fct_inscripcion",
    "rep_metricas_materia", "rep_promedio_generacion",
    "rep_extras_por_materia", "rep_optativas_mas_menos_elegidas",
    "errores_etl",
]

# ---------------------------------------------------------------- carga ---

def cargar_desde_mysql(engine):
    """Lee todas las tablas del data mart. Las que no existan quedan vacías."""
    dfs = {}
    for t in TABLAS:
        try:
            dfs[t] = pd.read_sql(f"SELECT * FROM {t}", engine)
        except Exception:
            dfs[t] = pd.DataFrame()
    return dfs


def _bool_col(df, col):
    """Normaliza una columna 0/1 o True/False de MySQL a booleano."""
    if col in df.columns:
        df[col] = df[col].fillna(0).astype(bool)
    return df


def preparar(dfs):
    """Junta los hechos con sus dimensiones. Devuelve dict con DataFrames
    listos para graficar: 'cal', 'ext', 'insc', más las dimensiones."""
    dim_al = dfs["dim_alumno"].copy()
    dim_as = dfs["dim_asignatura"].copy()
    dim_t = dfs["dim_tiempo"].copy()
    dim_v = dfs["dim_votacion"].copy()
    fct = dfs["fct_cal_alumno"].copy()
    ext = dfs["fct_extra_largo"].copy()
    ins = dfs["fct_inscripcion"].copy()

    for df, cols in [(fct, ["es_aprobatoria", "es_reprobada", "es_np", "es_na"]),
                     (dim_as, ["es_optativa"])]:
        for c in cols:
            _bool_col(df, c)

    # Orden canónico de periodos = el de dim_tiempo (id_periodo).
    orden_periodos = list(dim_t.sort_values("id_periodo")["periodo_unam"]) \
        if len(dim_t) else []

    # Etiqueta legible del periodo para las gráficas: "2027-1 (ago-dic 2026)".
    # Si se grafica el código ("20271") tal cual, Plotly lo lee como número
    # y pone el eje X en escala continua (2k, 4k... 18k). La etiqueta no es
    # numérica y además el eje se fuerza a categórico en cada gráfica.
    _ord = dim_t.sort_values("id_periodo")
    _etiq = {str(p): etiqueta_periodo(p, dd)
             for p, dd in zip(_ord["periodo_unam"], _ord["descripcion"])}
    _orden_etiq = [_etiq[str(p)] for p in _ord["periodo_unam"]]

    cal = (fct
           .merge(dim_al[["id_estudiante", "username", "nombre_completo",
                          "generacion", "sexo"]],
                  left_on="id_dim_estudiante", right_on="id_estudiante", how="left")
           .merge(dim_as[["id_asignatura", "clave", "nombre", "opt_ob", "es_optativa"]],
                  left_on="id_dim_asignatura", right_on="id_asignatura", how="left")
           .merge(dim_t[["id_periodo", "periodo_unam", "descripcion"]],
                  left_on="id_dim_periodo", right_on="id_periodo", how="left"))
    cal["periodo_unam"] = pd.Categorical(cal["periodo_unam"],
                                         categories=orden_periodos, ordered=True)
    cal["periodo_label"] = pd.Categorical(cal["periodo_unam"].astype(str).map(_etiq),
                                          categories=_orden_etiq, ordered=True)

    ext = (ext
           .merge(dim_al[["id_estudiante", "generacion", "sexo"]],
                  left_on="id_dim_estudiante", right_on="id_estudiante", how="left")
           .merge(dim_as[["id_asignatura", "clave", "nombre"]],
                  left_on="id_dim_asignatura", right_on="id_asignatura", how="left")
           .merge(dim_t[["id_periodo", "periodo_unam"]],
                  left_on="id_dim_periodo", right_on="id_periodo", how="left")
           .merge(dim_v[["id_votacion", "inicio", "fin"]],
                  left_on="id_dim_votacion", right_on="id_votacion", how="left"))
    ext["periodo_unam"] = pd.Categorical(ext["periodo_unam"],
                                         categories=orden_periodos, ordered=True)
    ext["periodo_label"] = pd.Categorical(ext["periodo_unam"].astype(str).map(_etiq),
                                          categories=_orden_etiq, ordered=True)

    ins = (ins
           .merge(dim_al[["id_estudiante", "generacion", "sexo"]],
                  left_on="id_dim_estudiante", right_on="id_estudiante", how="left")
           .merge(dim_as[["id_asignatura", "clave", "nombre", "opt_ob", "es_optativa"]],
                  left_on="id_dim_asignatura", right_on="id_asignatura", how="left"))

    return {"cal": cal, "ext": ext, "insc": ins,
            "dim_alumno": dim_al, "dim_asignatura": dim_as,
            "dim_tiempo": dim_t, "dim_votacion": dim_v,
            "orden_periodos": orden_periodos}


def filtrar_cal(cal, periodos=None, generaciones=None, sexos=None, tipos=None):
    """Aplica los filtros del menú lateral al hecho de calificaciones."""
    d = cal
    if periodos:
        d = d[d["periodo_unam"].isin(periodos)]
    if generaciones:
        d = d[d["generacion"].isin(generaciones)]
    if sexos:
        d = d[d["sexo"].isin(sexos)]
    if tipos:
        d = d[d["tipo_evaluacion"].isin(tipos)]
    return d

# ------------------------------------------------------------------ KPIs ---

def kpis(d):
    """Indicadores del resumen general (ya con filtros aplicados en 'cal')."""
    cal, ext, ins = d["cal"], d["ext"], d["insc"]
    evaluados = cal[~cal["es_np"]]
    aprob = int(cal["es_aprobatoria"].sum())
    repro = int(cal["es_reprobada"].sum())
    nps = int(cal["es_np"].sum())
    nas = int(cal["es_na"].sum())
    prom = float(cal["calificacion_num"].mean()) if cal["calificacion_num"].notna().any() else float("nan")
    denom = len(evaluados)
    return {
        "alumnos": int(cal["id_dim_estudiante"].nunique()) if len(cal) else 0,
        "evaluaciones": len(cal),
        "promedio": prom,
        "aprobados": aprob,
        "reprobados": repro,
        "np": nps,
        "na": nas,
        "ind_reprobacion": (repro / denom * 100) if denom else 0.0,
        "ind_aprovechamiento": (aprob / denom * 100) if denom else 0.0,
        "extras": int(ext["cantidad"].sum()) if len(ext) else 0,
        "inscripciones": int(ins["cantidad"].sum()) if len(ins) else 0,
    }


# ------------------------------------------------------- datos de ejemplo ---

def datos_demo(seed=42):
    """Datos sintéticos con el mismo esquema del data mart, para probar el
    tablero sin conectarse a MySQL (o para enseñarlo)."""
    rng = np.random.default_rng(seed)
    periodos = ["20211", "20212", "20221", "20222", "20231", "20232",
                "20241", "20242", "20251", "20252", "20261", "20262",
                "20271", "01012"]
    dim_t = pd.DataFrame([{
        "id_periodo": i + 1, "periodo_unam": p,
        "anio_ciclo": None if p == "01012" else int(p[:4]),
        "semestre_ciclo": None if p == "01012" else int(p[4]),
        "descripcion": "Extraordinarios sin periodo" if p == "01012"
                       else f"{'ago-dic' if p[4] == '1' else 'ene-jun'} {int(p[:4])}",
        "es_periodo_estandar": p != "01012",
    } for i, p in enumerate(periodos)])

    materias = [("1101", "Álgebra Superior I", "OB"), ("1102", "Cálculo Diferencial", "OB"),
                ("1103", "Geometría Analítica", "OB"), ("1104", "Lógica Matemática", "OB"),
                ("1105", "Álgebra Lineal", "OB"), ("1106", "Cálculo Integral", "OB"),
                ("1107", "Probabilidad I", "OB"), ("1108", "Estadística I", "OB"),
                ("1201", "Ecuaciones Diferenciales", "OB"), ("1202", "Análisis Numérico", "OB"),
                ("1203", "Bases de Datos", "OB"), ("1204", "Programación I", "OB"),
                ("1205", "Programación II", "OB"), ("1206", "Métodos Numéricos", "OB"),
                ("1207", "Física I", "OB"), ("1208", "Química General", "OB"),
                ("1301", "Optativa: Ciencia de Datos", "OP"), ("1302", "Optativa: IA", "OP"),
                ("1303", "Optativa: Criptografía", "OP"), ("1304", "Optativa: Robótica", "OP")]
    dim_as = pd.DataFrame([{
        "id_asignatura": i + 1, "clave": c, "nombre": n, "plan": 2020,
        "semestre_plan": (i % 8) + 1, "semestre_desc": f"Semestre {(i % 8) + 1}",
        "opt_ob": o, "es_optativa": o == "OP",
    } for i, (c, n, o) in enumerate(materias)])

    n_al = 400
    dim_al = pd.DataFrame({
        "id_estudiante": range(1, n_al + 1),
        "id_auth_user": range(1, n_al + 1),
        "username": [f"31{rng.integers(100000, 999999)}" for _ in range(n_al)],
        "nombre_completo": [f"Alumno Demo {i + 1}" for i in range(n_al)],
        "email": [f"alumno{i + 1}@demo.unam.mx" for i in range(n_al)],
        "generacion": rng.choice([2018, 2019, 2020, 2021, 2022, 2023, 2024], n_al),
        "sexo": rng.choice(["Hombre", "Mujer"], n_al, p=[0.55, 0.45]),
        "deleg_muni": rng.choice(["Acatlán", "Naucalpan", "Tlalnepantla", "Azcapotzalco"], n_al),
        "fecha_nac": pd.to_datetime("2000-01-01") + pd.to_timedelta(
            rng.integers(0, 365 * 8, n_al), unit="D"),
    })

    dim_v = pd.DataFrame([{
        "id_votacion": i + 1, "periodo_unam": p,
        "inicio": pd.Timestamp(f"20{p[:2]}-01-10") + pd.Timedelta(days=30 * i),
        "fin": pd.Timestamp(f"20{p[:2]}-01-10") + pd.Timedelta(days=30 * i + 14),
    } for i, p in enumerate(["20182", "20212", "20222", "20252", "20271"])])

    # Hecho de calificaciones: 6000 filas alumno+materia+periodo.
    n = 6000
    tipo = rng.choice(["O", "E"], n, p=[0.8, 0.2])
    estado = rng.choice(["APROBADA", "REPROBADA", "NP", "NA"],
                        n, p=[0.55, 0.14, 0.21, 0.10])
    num = np.where(estado == "APROBADA", rng.integers(6, 11, n).astype(float),
          np.where(estado == "REPROBADA", rng.integers(0, 6, n).astype(float), np.nan))
    orig = np.where(estado == "NP", "NP",
           np.where(estado == "NA", "NA",
           np.where((estado == "APROBADA") & (rng.random(n) < 0.25),
                    rng.choice(["MB", "B", "S"], n), num.astype(object).astype(str))))
    # Convierte "6.0" -> "06" para parecerse a los datos reales.
    orig = [f"{int(float(v)):02d}" if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v
            for v in orig]
    fct = pd.DataFrame({
        "id_hecho": range(1, n + 1),
        "id_dim_estudiante": rng.integers(1, n_al + 1, n),
        "id_dim_asignatura": rng.integers(1, len(materias) + 1, n),
        "id_dim_periodo": rng.integers(1, len(periodos) + 1, n),
        "calificacion_original": orig,
        "calificacion_num": num,
        "es_aprobatoria": estado == "APROBADA",
        "es_reprobada": np.isin(estado, ["REPROBADA", "NA"]),
        "es_np": estado == "NP",
        "es_na": estado == "NA",
        "estado_evaluacion": np.where(estado == "NA", "REPROBADA", estado),
        "acreditado": (estado == "APROBADA").astype(int),
        "tipo_evaluacion": tipo,
        "total_intentos": rng.integers(1, 4, n),
    }).drop_duplicates(subset=["id_dim_estudiante", "id_dim_asignatura", "id_dim_periodo"])

    m = 300
    ext = pd.DataFrame({
        "id_hecho": range(1, m + 1),
        "id_dim_estudiante": rng.integers(1, n_al + 1, m),
        "id_dim_asignatura": rng.integers(1, len(materias) + 1, m),
        "id_dim_periodo": rng.integers(1, len(periodos) + 1, m),
        "id_dim_votacion": rng.integers(1, 6, m),
        "fecha_voto": pd.to_datetime("2022-01-01") + pd.to_timedelta(
            rng.integers(0, 365 * 3, m), unit="D"),
        "cantidad": 1,
    })

    k = 1500
    ins = pd.DataFrame({
        "id_hecho": range(1, k + 1),
        "id_dim_estudiante": rng.integers(1, n_al + 1, k),
        "id_dim_asignatura": rng.integers(1, len(materias) + 1, k),
        "cantidad": 1,
    }).drop_duplicates(subset=["id_dim_estudiante", "id_dim_asignatura"])

    dfs = {"dim_alumno": dim_al, "dim_asignatura": dim_as, "dim_tiempo": dim_t,
           "dim_votacion": dim_v, "fct_cal_alumno": fct,
           "fct_extra_largo": ext, "fct_inscripcion": ins}
    for t in TABLAS:
        dfs.setdefault(t, pd.DataFrame())
    return dfs

# ------------------------------------------------- validación del esquema ---

COLUMNAS_REQUERIDAS = {
    "dim_alumno": ["id_estudiante", "id_auth_user", "username", "nombre_completo",
                   "generacion", "sexo"],
    "dim_asignatura": ["id_asignatura", "clave", "nombre", "opt_ob", "es_optativa"],
    "dim_tiempo": ["id_periodo", "periodo_unam"],
    "dim_votacion": ["id_votacion", "periodo_unam"],
    "fct_cal_alumno": ["id_hecho", "id_dim_estudiante", "id_dim_asignatura",
                       "id_dim_periodo", "calificacion_num", "es_aprobatoria",
                       "es_reprobada", "es_np", "es_na", "estado_evaluacion",
                       "tipo_evaluacion", "total_intentos"],
    "fct_extra_largo": ["id_hecho", "id_dim_estudiante", "id_dim_asignatura",
                        "id_dim_periodo", "id_dim_votacion", "cantidad"],
    "fct_inscripcion": ["id_hecho", "id_dim_estudiante", "id_dim_asignatura",
                        "cantidad"],
}


def validar(dfs):
    """Revisa que las tablas del data mart existan, tengan filas y las
    columnas que el tablero necesita. Devuelve la lista de problemas
    (vacía = todo OK). Sin esto, un esquema viejo truena con un KeyError
    críptico dentro de preparar()."""
    problemas = []
    for tabla, cols in COLUMNAS_REQUERIDAS.items():
        df = dfs.get(tabla)
        if df is None or len(df.columns) == 0:
            problemas.append(f"{tabla}: no existe o no se pudo leer "
                             f"(¿está cargada en data_mart_pagmac?)")
        elif len(df) == 0:
            problemas.append(f"{tabla}: existe pero está vacía (0 filas)")
        else:
            faltan = [c for c in cols if c not in df.columns]
            if faltan:
                problemas.append(f"{tabla}: faltan las columnas {faltan}")
    return problemas


# ---------------------------------------------------------------- gráficas ---
# Diseño: los periodos ("20271", "01012") son códigos, no números. Si se
# grafican tal cual, Plotly los interpreta como escala numérica continua y
# el eje X sale en 2k, 4k... 18k con las barras amontonadas a la derecha.
# Por eso: (1) el eje X usa la etiqueta legible "2027-1 (ago-dic 2026)"
# (columna periodo_label), y (2) todos los ejes de periodo, generación y
# calificación se fuerzan a categóricos (type="category"). Los colores son
# consistentes en todo el tablero: azul para conteos, verde/rojo/gris para
# aprobada/reprobada/NP, verde para extras (votaciones) y dorado para
# optativas. Las barras llevan su valor encima (text_auto).

AZUL = "#2e75b6"
AZUL_OSCURO = "#1f4e79"
DORADO = "#bf8f00"
VERDE_EXTRA = "#2e8b57"
ROJO = "#c0392b"
COLORES_ESTADO = {"APROBADA": "#2ca02c", "REPROBADA": "#d62728", "NP": "#7f7f7f"}


def etiqueta_periodo(p, descripcion):
    """Etiqueta legible para un periodo UNAM: '2027-1 (ago-dic 2026)'."""
    p = str(p)
    if p == "01012":
        return "01012 (extraord. sin periodo)"
    anio, sem = p[:4], p[4]
    if str(descripcion or "").startswith(f"{anio}-{sem}"):
        return str(descripcion)
    meses = "ago-dic" if sem == "1" else "ene-jun"
    anio_cal = int(anio) - 1 if sem == "1" else int(anio)
    return f"{anio}-{sem} ({meses} {anio_cal})"


def _estilo(fig, titulo, x_titulo=None, y_titulo=None, x_categoria=False):
    """Estilo común: títulos y ejes explícitos, letra legible, márgenes."""
    fig.update_layout(
        title={"text": titulo, "font": {"size": 17}},
        font={"size": 13},
        margin={"l": 70, "r": 30, "t": 70, "b": 80},
        hovermode="closest",
    )
    if x_titulo:
        fig.update_xaxes(title_text=x_titulo)
    if y_titulo:
        fig.update_yaxes(title_text=y_titulo)
    if x_categoria:
        # Sin esto, Plotly vuelve a tratar "20271" como número.
        fig.update_xaxes(type="category", tickangle=-45)
    return fig


def fig_alumnos_periodo(cal):
    g = (cal.groupby("periodo_label", observed=True)["id_dim_estudiante"]
            .nunique().reset_index(name="alumnos"))
    fig = px.bar(g, x="periodo_label", y="alumnos", text_auto=True,
                 color_discrete_sequence=[AZUL])
    return _estilo(fig, "Alumnos activos por periodo",
                    "Periodo UNAM", "Número de alumnos distintos",
                    x_categoria=True)


def fig_estado_periodo(cal):
    g = (cal.groupby(["periodo_label", "estado_evaluacion"], observed=True)
            .size().reset_index(name="evaluaciones"))
    fig = px.bar(g, x="periodo_label", y="evaluaciones", color="estado_evaluacion",
                 color_discrete_map=COLORES_ESTADO)
    fig = _estilo(fig, "Aprobadas, reprobadas y NP por periodo",
                  "Periodo UNAM", "Número de evaluaciones",
                  x_categoria=True)
    fig.update_layout(barmode="stack", legend_title_text="Estado")
    return fig


def fig_distribucion_calif(cal):
    d = cal[cal["calificacion_num"].notna()].copy()
    d["calificacion_num"] = d["calificacion_num"].astype(int).astype(str)
    orden = [str(i) for i in range(0, 11)]
    g = d.groupby("calificacion_num").size().reindex(orden, fill_value=0).reset_index(name="n")
    g = g[g["n"] > 0]
    fig = px.bar(g, x="calificacion_num", y="n", text_auto=True,
                 color_discrete_sequence=[AZUL_OSCURO])
    return _estilo(fig, "Distribución de calificaciones numéricas (NP y NA no tienen número)",
                   "Calificación (escala 0-10)", "Número de evaluaciones",
                   x_categoria=True)


def fig_reprobacion_materia(cal, top=10):
    ev = cal[~cal["es_np"]]
    g = (ev.groupby(["clave", "nombre"], observed=True)
           .agg(evaluados=("id_hecho", "size"),
                reprobados=("es_reprobada", "sum"))
           .reset_index())
    g = g[g["evaluados"] >= 20]
    g["ind_reprobacion"] = g["reprobados"] / g["evaluados"] * 100
    g = g.sort_values("ind_reprobacion", ascending=False).head(top)
    fig = px.bar(g, x="ind_reprobacion", y="nombre", orientation="h",
                 text_auto=".1f", color_discrete_sequence=[ROJO],
                 hover_data=["clave", "evaluados", "reprobados"])
    fig = _estilo(fig, f"Top {top} materias con mayor índice de reprobación",
                  "% de reprobados (sobre evaluados)", "Materia")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def fig_promedio_materia(cal, top=10, peores=False):
    g = (cal.groupby(["clave", "nombre"], observed=True)
           .agg(promedio=("calificacion_num", "mean"),
                evaluados=("calificacion_num", "count"))
           .reset_index())
    g = g[g["evaluados"] >= 20].sort_values("promedio", ascending=peores).head(top)
    fig = px.bar(g, x="promedio", y="nombre", orientation="h",
                 text_auto=".2f", color_discrete_sequence=[AZUL],
                 hover_data=["clave", "evaluados"])
    fig = _estilo(fig, f"Top {top} materias con {'menor' if peores else 'mayor'} promedio",
                  "Promedio (escala 0-10)", "Materia")
    fig.update_layout(yaxis={"categoryorder": "total ascending"}, xaxis_range=[0, 10])
    return fig


def fig_promedio_generacion(cal):
    g = (cal.groupby("generacion", observed=True)
           .agg(promedio=("calificacion_num", "mean"),
                alumnos=("id_dim_estudiante", "nunique"))
           .reset_index())
    g["generacion"] = g["generacion"].astype(str)
    fig = px.bar(g, x="generacion", y="promedio", text_auto=".2f",
                 color_discrete_sequence=[AZUL],
                 hover_data=["alumnos"])
    fig = _estilo(fig, "Promedio por generación",
                  "Generación", "Promedio (escala 0-10)",
                  x_categoria=True)
    fig.update_layout(yaxis_range=[0, 10])
    return fig


def fig_alumnos_generacion(dim_alumno):
    g = dim_alumno.groupby("generacion").size().reset_index(name="alumnos")
    g["generacion"] = g["generacion"].astype(str)
    fig = px.bar(g, x="generacion", y="alumnos", text_auto=True,
                 color_discrete_sequence=[AZUL])
    return _estilo(fig, "Alumnos por generación",
                   "Generación", "Número de alumnos",
                   x_categoria=True)


def fig_reprobacion_generacion(cal):
    ev = cal[~cal["es_np"]]
    g = (ev.groupby("generacion", observed=True)
           .agg(evaluados=("id_hecho", "size"),
                reprobados=("es_reprobada", "sum"))
           .reset_index())
    g["ind_reprobacion"] = g["reprobados"] / g["evaluados"] * 100
    g["generacion"] = g["generacion"].astype(str)
    fig = px.bar(g, x="generacion", y="ind_reprobacion", text_auto=".1f",
                 color_discrete_sequence=[ROJO],
                 hover_data=["evaluados", "reprobados"])
    return _estilo(fig, "Índice de reprobación por generación",
                   "Generación", "% de reprobados (sobre evaluados)",
                   x_categoria=True)


def fig_extras_materia(ext, top=10):
    g = (ext.groupby(["clave", "nombre"], observed=True)["cantidad"]
            .sum().reset_index(name="extras"))
    g = g.sort_values("extras", ascending=False).head(top)
    fig = px.bar(g, x="extras", y="nombre", orientation="h",
                 text_auto=True, color_discrete_sequence=[VERDE_EXTRA],
                 hover_data=["clave"])
    fig = _estilo(fig, f"Top {top} materias con más extras largos",
                  "Número de votos de extra largo", "Materia")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def fig_extras_periodo(ext):
    g = (ext.groupby("periodo_label", observed=True)["cantidad"]
            .sum().reset_index(name="extras"))
    fig = px.bar(g, x="periodo_label", y="extras", text_auto=True,
                 color_discrete_sequence=[VERDE_EXTRA])
    return _estilo(fig, "Extras largos por periodo",
                   "Periodo UNAM", "Número de votos",
                   x_categoria=True)


def fig_optativas(insc):
    d = insc[insc["es_optativa"] == True]  # noqa: E712
    g = (d.groupby(["clave", "nombre"], observed=True)["cantidad"]
            .sum().reset_index(name="inscripciones"))
    g = g.sort_values("inscripciones", ascending=False)
    fig = px.bar(g, x="inscripciones", y="nombre", orientation="h",
                 text_auto=True, color_discrete_sequence=[DORADO],
                 hover_data=["clave"])
    fig = _estilo(fig, "Optativas: inscripciones por materia (más a menos elegidas)",
                  "Número de inscripciones", "Materia")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def fig_inscritos_materia(insc, top=10):
    g = (insc.groupby(["clave", "nombre"], observed=True)["cantidad"]
            .sum().reset_index(name="inscripciones"))
    g = g.sort_values("inscripciones", ascending=False).head(top)
    fig = px.bar(g, x="inscripciones", y="nombre", orientation="h",
                 text_auto=True, color_discrete_sequence=[AZUL],
                 hover_data=["clave"])
    fig = _estilo(fig, f"Top {top} materias con más inscritos",
                  "Número de inscripciones", "Materia")
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    return fig


def fig_sexo(dim_alumno):
    g = dim_alumno.groupby("sexo").size().reset_index(name="alumnos")
    fig = px.pie(g, names="sexo", values="alumnos",
                 title="Alumnos por sexo",
                 color_discrete_sequence=[AZUL, "#c76da2"])
    fig.update_layout(title={"font": {"size": 17}}, font={"size": 13})
    return fig
