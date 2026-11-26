import sys

import fsspec
import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling
from rasterio.mask import mask
from rasterio.transform import array_bounds
from rasterio.windows import from_bounds
from pystac_client import Client
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

pol, parc, rec = (int(x) for x in sys.argv[1:4]) if len(sys.argv) >= 4 else (1, 75, 1)
etiqueta = f"{pol}-{parc}-{rec}"
CLASES_VALIDAS = [4, 5]  # SCL: 4 = vegetación, 5 = suelo desnudo

cand = gpd.read_file("data/candidatas.gpkg", layer="candidatas")
p = cand[(cand.poligono == pol) & (cand.parcela == parc) & (cand.recinto == rec)].iloc[0]
parcela = gpd.GeoSeries([p.geometry], crs=cand.crs)
bbox = [float(x) for x in parcela.to_crs(4326).total_bounds]

cliente = Client.open("https://earth-search.aws.element84.com/v1")
items = list(cliente.search(
    collections=["sentinel-2-l2a"], bbox=bbox,
    datetime="2024-10-01/2025-07-15",
    query={"eo:cloud_cover": {"lt": 70}},
).items())

por_fecha = {}
for it in items:
    d = it.datetime.date()
    if d not in por_fecha or it.properties["eo:cloud_cover"] < por_fecha[d].properties["eo:cloud_cover"]:
        por_fecha[d] = it
print(f"Parcela {etiqueta}: {len(items)} escenas -> {len(por_fecha)} fechas distintas", flush=True)

fs = fsspec.filesystem("https", client_kwargs={"trust_env": True}, block_size=512 * 1024)


def procesar(it):
    with rasterio.open(it.assets["red"].href, opener=fs) as src:
        interior = parcela.to_crs(src.crs).buffer(-10)
        rojo, transf = mask(src, interior, crop=True)
    with rasterio.open(it.assets["nir"].href, opener=fs) as src:
        nir, _ = mask(src, interior, crop=True)
    alto, ancho = rojo.shape[1:]
    limites = array_bounds(alto, ancho, transf)
    with rasterio.open(it.assets["scl"].href, opener=fs) as src:
        scl = src.read(1, window=from_bounds(*limites, transform=src.transform),
                       out_shape=(alto, ancho), resampling=Resampling.nearest)
    r, n = rojo[0].astype("float32"), nir[0].astype("float32")
    con_dato = (r > 0) & (n > 0)
    validos = con_dato & np.isin(scl, CLASES_VALIDAS)
    ndvi = (n[validos] - r[validos]) / (n[validos] + r[validos])
    return {
        "fecha": it.datetime.date(), "escena": it.id,
        "nubes_escena": round(it.properties["eo:cloud_cover"], 1),
        "px_con_dato": int(con_dato.sum()), "px_validos": int(validos.sum()),
        "ndvi_media": float(ndvi.mean()) if ndvi.size else np.nan,
        "ndvi_mediana": float(np.median(ndvi)) if ndvi.size else np.nan,
    }


filas = []
for i, (fecha, it) in enumerate(sorted(por_fecha.items()), 1):
    try:
        fila = procesar(it)
        filas.append(fila)
        print(f"{i}/{len(por_fecha)} {fecha} válidos {fila['px_validos']}/{fila['px_con_dato']} NDVI {fila['ndvi_media']:.2f}", flush=True)
    except Exception as e:
        print(f"{i}/{len(por_fecha)} {fecha} ERROR: {e!r}", flush=True)
    pd.DataFrame(filas).to_csv(f"data/serie_ndvi_{etiqueta}.csv", index=False)

df = pd.DataFrame(filas)
buenas = df[(df.px_con_dato > 0) & (df.px_validos >= 0.5 * df.px_con_dato)]
print(f"{len(buenas)} fechas útiles de {len(df)}")

fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(buenas.fecha, buenas.ndvi_media, "o-", color="tab:green")
ax.set_ylim(0, 1)
ax.set_ylabel("NDVI (media del interior)")
ax.set_title(f"Parcela {etiqueta}: campaña 2024-25 (píxeles sin nube)")
ax.grid(alpha=0.3)
fig.autofmt_xdate()
fig.savefig(f"data/serie_ndvi_{etiqueta}.png", dpi=150, bbox_inches="tight")
