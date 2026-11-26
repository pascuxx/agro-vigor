import fsspec
import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask
from pystac_client import Client
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

cand = gpd.read_file("data/candidatas.gpkg", layer="candidatas")
p = cand[(cand.poligono == 1) & (cand.parcela == 75) & (cand.recinto == 1)].iloc[0]
bbox = [float(x) for x in gpd.GeoSeries([p.geometry], crs=cand.crs).to_crs(4326).total_bounds]

cliente = Client.open("https://earth-search.aws.element84.com/v1")
items = list(cliente.search(
    collections=["sentinel-2-l2a"], bbox=bbox,
    datetime="2025-04-01/2025-05-31",
    query={"eo:cloud_cover": {"lt": 20}},
).items())
item = min(items, key=lambda i: i.properties["eo:cloud_cover"])
print("Escena:", item.id, "| nubes:", item.properties["eo:cloud_cover"])

fs = fsspec.filesystem("https", client_kwargs={"trust_env": True}, block_size=512 * 1024)


def leer(nombre):
    asset = item.assets[nombre]
    banda = asset.extra_fields["raster:bands"][0]
    escala, desfase = 0.0001, 0.0  # DN sin desplazamiento (verificado: rojo mín 188 < 1000)
    with rasterio.open(asset.href, opener=fs) as src:
        geom = gpd.GeoSeries([p.geometry], crs=cand.crs).to_crs(src.crs)
        datos, _ = mask(src, geom, crop=True)
    print(nombre, "-> escala", escala, "desfase", desfase, "| recorte:", datos.shape)
    dn = datos[0].astype("float32")
    return np.where(dn == 0, np.nan, dn * escala + desfase)


rojo, nir = leer("red"), leer("nir")
ndvi = (nir - rojo) / (nir + rojo)
assert np.nanmin(ndvi) >= -1 and np.nanmax(ndvi) <= 1, "NDVI fuera de rango: revisar escala y desfase"
print(f"NDVI: media {np.nanmean(ndvi):.2f}, mín {np.nanmin(ndvi):.2f}, máx {np.nanmax(ndvi):.2f}, píxeles {np.sum(~np.isnan(ndvi))}")

plt.imshow(ndvi, cmap="RdYlGn", vmin=0, vmax=1)
plt.colorbar(label="NDVI")
plt.title(f"Parcela 1-75 | {item.datetime.date()}")
plt.axis("off")
plt.savefig("data/ndvi_1-75.png", dpi=150, bbox_inches="tight")
