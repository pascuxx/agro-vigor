import json
import geopandas as gpd

todas = gpd.read_file("data/tricio_cebada.gpkg", layer="cebada")
cand = gpd.read_file("data/candidatas.gpkg", layer="candidatas")
claves = {(int(a), int(b), int(c)) for a, b, c in zip(cand.poligono, cand.parcela, cand.recinto)}

todas["geometry"] = todas.geometry.simplify(0.5)
minx, miny, maxx, maxy = todas.total_bounds
escala = 1000 / (maxx - minx)
alto = (maxy - miny) * escala


def ruta(geom):
    poligonos = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
    partes = []
    for pol in poligonos:
        for anillo in [pol.exterior, *pol.interiors]:
            pts = [f"{(x - minx) * escala:.1f},{(maxy - y) * escala:.1f}" for x, y in anillo.coords]
            partes.append("M" + " L".join(pts) + "Z")
    return " ".join(partes)


datos = []
for _, f in todas.iterrows():
    clave = (int(f.poligono), int(f.parcela), int(f.recinto))
    datos.append({
        "pol": clave[0], "parc": clave[1], "rec": clave[2],
        "ha": round(float(f.ha), 2), "riego": f.parc_sistexp,
        "cand": clave in claves, "d": ruta(f.geometry),
    })

PLANTILLA = r"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8"><title>Cebada 2025 en Tricio</title>
<style>
body{font-family:system-ui,sans-serif;margin:0;display:flex;height:100vh}
#panel{width:260px;padding:16px;border-right:1px solid #ddd;box-sizing:border-box}
label{display:block;margin-top:12px;font-size:13px}
select,button{width:100%;padding:6px;margin-top:4px}
#info{margin-top:16px;font-size:14px;line-height:1.5}
#mapa{flex:1;padding:8px;box-sizing:border-box}
svg{width:100%;height:100%}
path{stroke:#fff;stroke-width:0.4;fill-rule:evenodd}
.ley{margin-top:20px;font-size:13px}
.ley i{display:inline-block;width:12px;height:12px;margin-right:6px;vertical-align:middle}
</style></head><body>
<div id="panel">
<h3>Cebada 2025 en Tricio</h3>
<label>Polígono<select id="pol"></select></label>
<label>Parcela<select id="parc"></select></label>
<label>Recinto<select id="rec"></select></label>
<button id="reset">Limpiar</button>
<div id="info"></div>
<div class="ley">
<div><i style="background:#16a34a"></i>Selección</div>
<div><i style="background:#d62728"></i>Candidata</div>
<div><i style="background:#d3d3d3"></i>Otros recintos de cebada</div>
</div></div>
<div id="mapa"><svg id="svg"></svg></div>
<script>
const datos = __DATOS__;
const sel = {pol: document.getElementById("pol"), parc: document.getElementById("parc"), rec: document.getElementById("rec")};
const info = document.getElementById("info");
const svg = document.getElementById("svg");
svg.setAttribute("viewBox", "0 0 1000 __ALTO__");
const ns = "http://www.w3.org/2000/svg";
const caminos = datos.map(d => {
  const p = document.createElementNS(ns, "path");
  p.setAttribute("d", d.d);
  const t = document.createElementNS(ns, "title");
  t.textContent = d.pol + "-" + d.parc + "-r" + d.rec + " · " + d.ha + " ha · " + (d.riego === "S" ? "secano" : "regadío");
  p.appendChild(t);
  svg.appendChild(p);
  return p;
});
function unicos(campo, filtro) {
  return [...new Set(datos.filter(filtro).map(d => d[campo]))].sort((a, b) => a - b);
}
function rellenar(select, valores, etiqueta) {
  const actual = select.value;
  select.innerHTML = '<option value="">' + etiqueta + '</option>' + valores.map(v => '<option value="' + v + '">' + v + '</option>').join("");
  if (valores.map(String).includes(actual)) select.value = actual;
}
function actualizar() {
  const pol = sel.pol.value;
  rellenar(sel.parc, unicos("parc", d => !pol || d.pol == pol), "Todas");
  const parc = sel.parc.value;
  rellenar(sel.rec, unicos("rec", d => (!pol || d.pol == pol) && (!parc || d.parc == parc)), "Todos");
  const rec = sel.rec.value;
  const activo = pol || parc || rec;
  let n = 0, ultimo = null;
  datos.forEach((d, i) => {
    const ok = (!pol || d.pol == pol) && (!parc || d.parc == parc) && (!rec || d.rec == rec);
    if (activo && ok) { caminos[i].setAttribute("fill", "#16a34a"); svg.appendChild(caminos[i]); n++; ultimo = d; }
    else caminos[i].setAttribute("fill", d.cand ? "#d62728" : "#d3d3d3");
  });
  if (!activo) info.textContent = "Elige polígono, parcela y recinto.";
  else if (n === 1) info.innerHTML = "<b>" + ultimo.pol + "-" + ultimo.parc + "-r" + ultimo.rec + "</b><br>" + ultimo.ha + " ha · " + (ultimo.riego === "S" ? "secano" : "regadío") + "<br>" + (ultimo.cand ? "Candidata" : "No candidata");
  else info.textContent = n + " recintos coinciden";
}
sel.pol.onchange = () => { sel.parc.value = ""; sel.rec.value = ""; actualizar(); };
sel.parc.onchange = () => { sel.rec.value = ""; actualizar(); };
sel.rec.onchange = actualizar;
document.getElementById("reset").onclick = () => { sel.pol.value = ""; sel.parc.value = ""; sel.rec.value = ""; actualizar(); };
rellenar(sel.pol, unicos("pol", () => true), "Todos");
actualizar();
</script></body></html>"""

html = PLANTILLA.replace("__DATOS__", json.dumps(datos, ensure_ascii=False)).replace("__ALTO__", f"{alto:.0f}")
with open("data/mapa_parcelas.html", "w", encoding="utf-8") as f:
    f.write(html)
print(len(datos), "recintos escritos en data/mapa_parcelas.html")
