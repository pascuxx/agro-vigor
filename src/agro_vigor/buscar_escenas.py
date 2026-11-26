import geopandas as gpd
from pystac_client import Client

cand = gpd.read_file("data/candidatas.gpkg", layer="candidatas")
p = cand[(cand.poligono == 1) & (cand.parcela == 75) & (cand.recinto == 1)].iloc[0]
parcela = gpd.GeoSeries([p.geometry], crs=cand.crs).to_crs(4326)
bbox = [float(x) for x in parcela.total_bounds]
print("bbox:", [round(x, 5) for x in bbox])

cliente = Client.open("https://earth-search.aws.element84.com/v1")
busqueda = cliente.search(
    collections=["sentinel-2-l2a"],
    bbox=bbox,
    datetime="2024-10-01/2025-07-15",
    query={"eo:cloud_cover": {"lt": 60}},
)
items = list(busqueda.items())
print(len(items), "escenas")
for it in sorted(items, key=lambda i: i.datetime)[:8]:
    print(it.datetime.date(), it.properties["eo:cloud_cover"], it.id)
