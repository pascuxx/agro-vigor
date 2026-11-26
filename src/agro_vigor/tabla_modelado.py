import pandas as pd

HORIZONTES = [14, 28]                      # días a predecir
INICIO, FIN = "2025-02-10", "2025-06-16"   # ventana de la fecha t
MAX_HUECO = 25                             # días máximos a interpolar

u = pd.read_csv("data/series_ndvi_limpia.csv", parse_dates=["fecha"])
tabla = u.pivot(index="fecha", columns="parcela", values="ndvi_media")

diaria = tabla.reindex(pd.date_range(tabla.index.min(), tabla.index.max(), freq="D"))
diaria = diaria.interpolate(method="time", limit=MAX_HUECO, limit_area="inside")

filas = []
for h in HORIZONTES:
    for parcela in diaria.columns:
        s = diaria[parcela]
        df = pd.DataFrame({
            "ndvi_t": s,
            "ndvi_t_7": s.shift(7),
            "ndvi_t_14": s.shift(14),
            "y": s.shift(-h),
        })
        df["pendiente_14"] = df.ndvi_t - df.ndvi_t_14
        df["doy"] = df.index.dayofyear
        df["horizonte"] = h
        df["parcela"] = parcela
        df["poligono"] = int(parcela.split("-")[0])
        df = df.loc[INICIO:FIN].iloc[::7].dropna()
        filas.append(df.rename_axis("fecha").reset_index())

tm = pd.concat(filas, ignore_index=True)
tm.to_csv("data/tabla_modelado.csv", index=False)
print(tm.groupby("horizonte").size())
print(tm.poligono.value_counts().sort_index())
print(tm.head())
