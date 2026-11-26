import fsspec
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.windows import Window, bounds as bounds_ventana, from_bounds
from pystac_client import Client
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CLASES_VALIDAS = [4, 5]  # SCL: 4 = vegetación, 5 = suelo desnudo
UMBRAL = 0.9  # fracción mínima de píxeles válidos para dar una fecha por buena

cand = gpd.read_file("data/candidatas.gpkg", layer="candidatas").reset_index(drop=True)
cand["id"] = cand.poligono.astype(str) + "-" + cand.parcela.astype(str) + "-" + cand.recinto.astype(str)
interiores = cand.geometry.buffer(-10)
bbox = [float(x) for x in cand.to_crs(4326).total_bounds]

cliente = Client.open("https://earth-search.aws.element84.com/v1")
items = list(cliente.search(
    collections=["sentinel-2-l2a"], bbox=bbox,
    datetime="2024-10-01/2025-07-15",
    query={"eo:cloud_cover": {"lt": 70}},
).items())
items.sort(key=lambda i: i.datetime)
print(f"{len(cand)} parcelas, {len(items)} escenas", flush=True)

fs = fsspec.filesystem("https", client_kwargs={"trust_env": True}, block_size=512 * 1024)


def ventana(src, limites):
    izq, abajo, der, arriba = limites
    c0, f0 = ~src.transform * (izq, arriba)
    c1, f1 = ~src.transform * (der, abajo)
    c0, f0, c1, f1 = int(np.floor(c0)), int(np.floor(f0)), int(np.ceil(c1)), int(np.ceil(f1))
    return Window(c0, f0, c1 - c0, f1 - f0)


def procesar(it):
    with rasterio.open(it.assets["red"].href, opener=fs) as src:
        geoms = interiores.to_crs(src.crs)
        try:
            win = ventana(src, geoms.total_bounds).intersection(Window(0, 0, src.width, src.height))
        except WindowError:
            return []
        rojo = src.read(1, window=win).astype("float32")
        transf = src.window_transform(win)
        lim = bounds_ventana(win, src.transform)
    with rasterio.open(it.assets["nir"].href, opener=fs) as src:
        nir = src.read(1, window=win).astype("float32")
    with rasterio.open(it.assets["scl"].href, opener=fs) as src:
        scl = src.read(1, window=from_bounds(*lim, transform=src.transform),
                       out_shape=rojo.shape, resampling=Resampling.nearest)
    con_dato = (rojo > 0) & (nir > 0)
    ndvi = np.full(rojo.shape, np.nan, dtype="float32")
    ndvi[con_dato] = (nir[con_dato] - rojo[con_dato]) / (nir[con_dato] + rojo[con_dato])
    buenos = con_dato & np.isin(scl, CLASES_VALIDAS)
    filas = []
    for idp, g in zip(cand["id"], geoms):
        dentro = features.geometry_mask([g], out_shape=rojo.shape, transform=transf, invert=True)
        sel = dentro & buenos
        filas.append({
            "fecha": it.datetime.date(), "escena": it.id, "parcela": idp,
            "px_con_dato": int((dentro & con_dato).sum()), "px_validos": int(sel.sum()),
            "ndvi_media": float(ndvi[sel].mean()) if sel.any() else np.nan,
        })
    return filas


todas = []
for i, it in enumerate(items, 1):
    try:
        filas = procesar(it)
        todas += filas
        con = sum(1 for f in filas if f["px_validos"] > 0)
        print(f"{i}/{len(items)} {it.datetime.date()} {it.id} parcelas con píxeles válidos: {con}/{len(cand)}", flush=True)
    except Exception as e:
        print(f"{i}/{len(items)} {it.id} ERROR: {e!r}", flush=True)
    pd.DataFrame(todas).to_csv("data/series_ndvi_todas.csv", index=False)

df = pd.DataFrame(todas)
df["fraccion"] = df.px_validos / df.px_con_dato.where(df.px_con_dato > 0)
df = df.sort_values(["parcela", "fecha", "px_validos"], ascending=[True, True, False])
df = df.drop_duplicates(["parcela", "fecha"])
utiles = df[df.fraccion >= UMBRAL]
utiles.to_csv("data/series_ndvi_utiles.csv", index=False)
print(f"{len(df)} pares fecha-parcela; {len(utiles)} útiles (≥{UMBRAL:.0%} de píxeles válidos)")

tabla = utiles.pivot(index="fecha", columns="parcela", values="ndvi_media")
fig, ax = plt.subplots(figsize=(11, 5))
for col in tabla:
    s = tabla[col].dropna()
    ax.plot(s.index, s.values, lw=0.8, alpha=0.5)
ax.set_ylim(0, 1)
ax.set_ylabel("NDVI (media del interior)")
ax.set_title(f"{tabla.shape[1]} parcelas de cebada en Tricio, campaña 2024-25")
ax.grid(alpha=0.3)
fig.autofmt_xdate()
fig.savefig("data/series_ndvi_todas.png", dpi=150, bbox_inches="tight")
