
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse, StreamingResponse
from typing import Optional, List
import requests
import xml.etree.ElementTree as ET
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = FastAPI(
    title="API de Ensayos Clínicos",
    description="API para consultar y analizar información sobre ensayos clínicos.",
    version="1.0.0"
)


# -------------------- BUSCAR ENSAYOS --------------------
@app.get("/buscar_ensayos")
def buscar_ensayos(
    molecula: Optional[str] = None,
    patologia: Optional[str] = None,
    estado: Optional[str] = None,
    fase: Optional[str] = None,
    pais: Optional[str] = None,
    formato: Optional[str] = "json"
):
    if not molecula and not patologia:
        return {"error": "Debe especificar al menos 'molecula' o 'patologia'"}

    rss_url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"
    try:
        response = requests.get(rss_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        ensayos = []
        for item in root.findall(".//item"):
            titulo = item.find("title").text or ""
            link = item.find("link").text or ""
            ensayo_id = link.split("/")[-1] if link else "N/A"
            estado_estudio = "En curso"
            fase_estudio = "3" if "phase 3" in titulo.lower() else "Desconocida"
            ubicacion = "Desconocida"

            if estado and estado.lower() not in estado_estudio.lower():
                continue
            if fase and fase.lower() != fase_estudio.lower():
                continue
            if pais and pais.lower() not in ubicacion.lower():
                continue

            ensayos.append({
                "identificador": ensayo_id,
                "titulo": titulo,
                "estado": estado_estudio,
                "fase": fase_estudio,
                "ubicacion": ubicacion
            })

        if formato == "texto":
            resumen = f"Se encontraron {len(ensayos)} ensayos clínicos:\n\n"
            for i, ensayo in enumerate(ensayos[:10], 1):
                resumen += f"{i}. {ensayo['titulo']} (ID: {ensayo['identificador']})\n"
            return PlainTextResponse(content=resumen)

        return {"ensayos": ensayos}

    except Exception as e:
        return {"error": str(e)}


# -------------------- DETALLE ENSAYO --------------------
@app.get("/ensayo_detalle")
def ensayo_detalle(id: str):
    url = f"https://clinicaltrials.gov/ct2/show/{id}?displayxml=true"
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        def get_text(path):
            el = root.find(path)
            return el.text if el is not None else "No disponible"

        return {
            "id": id,
            "titulo": get_text(".//official_title") or get_text(".//brief_title"),
            "resumen": get_text(".//brief_summary/textblock"),
            "estado": get_text(".//overall_status"),
            "fase": get_text(".//phase"),
            "tipo_estudio": get_text(".//study_type"),
            "patrocinador": get_text(".//lead_sponsor/agency"),
            "fecha_inicio": get_text(".//start_date"),
            "condiciones": [el.text for el in root.findall(".//condition")],
            "intervenciones": [el.text for el in root.findall(".//intervention/intervention_name")],
            "ubicaciones": [el.text for el in root.findall(".//location/facility/name")],
            "criterios": get_text(".//eligibility/criteria/textblock")
        }

    except Exception as e:
        return {"error": f"No se pudo obtener el detalle del ensayo: {str(e)}"}


# -------------------- CRITERIOS POR ID --------------------
@app.get("/criterios_ensayo")
def criterios_ensayo(id: str):
    try:
        url = f"https://clinicaltrials.gov/ct2/show/{id}?displayxml=true"
        r = requests.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        criterios = root.find(".//eligibility/criteria/textblock")
        return {
            "id": id,
            "criterios_inclusion_exclusion": criterios.text if criterios is not None else "No disponible"
        }
    except Exception as e:
        return {"error": str(e)}


# -------------------- COMPARAR MOLÉCULAS --------------------
@app.get("/comparar_moleculas")
def comparar_moleculas(molecula1: str, molecula2: str, patologia: str):
    def contar(mol):
        try:
            url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={mol}&cond={patologia}"
            r = requests.get(url)
            r.raise_for_status()
            return len(ET.fromstring(r.content).findall(".//item"))
        except:
            return 0

    return {
        molecula1: contar(molecula1),
        molecula2: contar(molecula2),
        "patologia": patologia
    }


# -------------------- ENDPOINT ANALYSIS --------------------
@app.get("/analisis_endpoint")
def analisis_endpoint(patologia: str, fase: Optional[str] = None):
    comunes = {
        "cáncer": ["supervivencia global", "respuesta objetiva"],
        "diabetes": ["HbA1c", "peso corporal"],
        "vitiligo": ["re-pigmentación", "mejora de VASI"]
    }
    return {
        "patologia": patologia,
        "fase": fase,
        "endpoints_comunes": comunes.get(patologia.lower(), ["No especificados"])
    }


# -------------------- PICO SUGERIDO (+ PDF) --------------------
@app.get("/pico_sugerido")
def pico_sugerido(molecula: str, patologia: str, formato: Optional[str] = "json"):
    pico = {
        "Paciente": f"Pacientes con {patologia}",
        "Intervención": molecula,
        "Comparador": "Placebo o tratamiento estándar",
        "Outcome": "Mejora clínica significativa"
    }

    if formato == 'pdf':
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, f"Esquema PICO - {molecula} / {patologia}")
        c.setFont("Helvetica", 12)
        y = height - 100
        for clave, valor in pico.items():
            c.drawString(50, y, f"{clave}: {valor}")
            y -= 30
        c.save()
        buffer.seek(0)
        return StreamingResponse(buffer, media_type='application/pdf', headers={
            "Content-Disposition": f"attachment;filename=pico_{molecula}.pdf"
        })

    return pico


# -------------------- TENDENCIAS DE INVESTIGACIÓN --------------------
@app.get("/tendencias_investigacion")
def tendencias_investigacion(patologia: str):
    datos = {
        "vitiligo": {
            "moleculas_en_alza": ["ruxolitinib", "tofacitinib", "baricitinib"],
            "endpoints_frecuentes": ["mejora del VASI", "calidad de vida", "re-pigmentación facial"],
            "zonas_con_mayor_actividad": ["EEUU", "India", "España"],
            "nuevos_estudios_por_año": {
                "2021": 6, "2022": 10, "2023": 14, "2024": 18
            }
        },
        "diabetes": {
            "moleculas_en_alza": ["semaglutida", "tirzepatida", "dapagliflozina"],
            "endpoints_frecuentes": ["HbA1c", "peso corporal", "riesgo CV"],
            "zonas_con_mayor_actividad": ["EEUU", "México", "Brasil"],
            "nuevos_estudios_por_año": {
                "2021": 20, "2022": 25, "2023": 30, "2024": 34
            }
        }
    }

    if patologia.lower() not in datos:
        return {"error": f"No hay datos simulados para {patologia}"}

    return {"patologia": patologia, **datos[patologia.lower()]}


# -------------------- RESUMEN CLÍNICO DE MOLÉCULA --------------------
@app.get("/resumen_molecula")
def resumen_molecula(molecula: str, patologia: str):
    try:
        url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = root.findall(".//item")

        cantidad = len(items)
        fases_detectadas = []
        for item in items:
            titulo = item.find("title").text or ""
            if "phase 1" in titulo.lower(): fases_detectadas.append("Fase 1")
            if "phase 2" in titulo.lower(): fases_detectadas.append("Fase 2")
            if "phase 3" in titulo.lower(): fases_detectadas.append("Fase 3")

        fases_unicas = list(set(fases_detectadas))
        recomendacion = "Revisión favorable" if "Fase 3" in fases_unicas else "Revisión preliminar"

        return {
            "molécula": molecula,
            "patología": patologia,
            "ensayos_encontrados": cantidad,
            "fases_detectadas": fases_unicas or ["No especificadas"],
            "centros_participantes_estimados": f"{min(5 + cantidad, 50)} (estimación)",
            "recomendación": recomendacion,
            "observaciones": "Resumen automático. Requiere evaluación experta."
        }

    except Exception as e:
        return {"error": str(e)}

# -------------------- EXPORTAR ENSAYOS EN PDF --------------------
@app.get("/exportar_ensayos_pdf")
def exportar_ensayos_pdf(molecula: str, patologia: Optional[str] = None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, height - 50, f"Exportación de Ensayos - {molecula}")
    c.setFont("Helvetica", 12)
    c.drawString(50, height - 90, f"Patología: {patologia or 'No especificada'}")
    c.drawString(50, height - 120, "Este es un ejemplo de exportación en PDF.")

    c.save()
    buffer.seek(0)
    return StreamingResponse(buffer, media_type='application/pdf', headers={
        "Content-Disposition": f"attachment;filename=ensayos_{molecula}.pdf"
    })

# -------------------- EXPORTAR ENSAYOS EN CSV --------------------
@app.get("/exportar_ensayos_csv")
def exportar_ensayos_csv(molecula: str, patologia: Optional[str] = None):
    output = io.StringIO()
    output.write("ID,Título,Estado,Fase\n")
    for i in range(1, 6):
        output.write(f"NCT000{i},Ensayo simulado {i},En curso,Fase 3\n")
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type='text/csv', headers={
        "Content-Disposition": f"attachment;filename=ensayos_{molecula}.csv"
    })
