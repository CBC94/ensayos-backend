from flask import Flask, request, jsonify, Response
import requests
import xml.etree.ElementTree as ET
import os
import csv
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)

# -------------------- BUSCAR ENSAYOS --------------------
@app.route('/buscar_ensayos', methods=['GET'])
def buscar_ensayos():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia', '')
    formato = request.args.get('formato', 'json')
    filtro_estado = request.args.get('estado', '').lower()
    filtro_fase = request.args.get('fase', '').lower()
    filtro_pais = request.args.get('pais', '').lower()

    if not molecula and not patologia:
        return jsonify({"error": "Debe especificar al menos 'molecula' o 'patologia'"}), 400

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
            estado = "En curso"
            fase = "3" if "phase 3" in titulo.lower() else "Desconocida"
            ubicacion = "Desconocida"

            if filtro_estado and filtro_estado not in estado.lower():
                continue
            if filtro_fase and filtro_fase != fase.lower():
                continue
            if filtro_pais and filtro_pais not in ubicacion.lower():
                continue

            ensayos.append({
                "identificador": ensayo_id,
                "titulo": titulo,
                "estado": estado,
                "fase": fase,
                "ubicacion": ubicacion
            })

        if formato == 'texto':
            resumen = f"Se encontraron {len(ensayos)} ensayos clínicos:\n\n"
            for i, ensayo in enumerate(ensayos[:10], 1):
                resumen += f"{i}. {ensayo['titulo']} (ID: {ensayo['identificador']})\n"
            return resumen, 200, {'Content-Type': 'text/plain; charset=utf-8'}

        return jsonify({"ensayos": ensayos})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- DETALLE ENSAYO --------------------
@app.route('/ensayo_detalle', methods=['GET'])
def ensayo_detalle():
    ensayo_id = request.args.get('id')
    if not ensayo_id:
        return jsonify({"error": "El parámetro 'id' es obligatorio"}), 400

    url = f"https://clinicaltrials.gov/ct2/show/{ensayo_id}?displayxml=true"

    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        def get_text(path):
            el = root.find(path)
            return el.text if el is not None else "No disponible"

        return jsonify({
            "id": ensayo_id,
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
        })

    except Exception as e:
        return jsonify({"error": f"No se pudo obtener el detalle del ensayo: {str(e)}"}), 500

# -------------------- CRITERIOS POR ID --------------------
@app.route('/criterios_ensayo', methods=['GET'])
def criterios_ensayo():
    ensayo_id = request.args.get('id')
    if not ensayo_id:
        return jsonify({"error": "El parámetro 'id' es obligatorio"}), 400

    try:
        url = f"https://clinicaltrials.gov/ct2/show/{ensayo_id}?displayxml=true"
        r = requests.get(url)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        criterios = root.find(".//eligibility/criteria/textblock")
        return jsonify({
            "id": ensayo_id,
            "criterios_inclusion_exclusion": criterios.text if criterios is not None else "No disponible"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- COMPARAR MOLÉCULAS --------------------
@app.route('/comparar_moleculas', methods=['GET'])
def comparar_moleculas():
    mol1 = request.args.get('molecula1')
    mol2 = request.args.get('molecula2')
    patologia = request.args.get('patologia')
    if not mol1 or not mol2 or not patologia:
        return jsonify({"error": "Faltan parámetros obligatorios"}), 400

    def contar(mol):
        try:
            url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={mol}&cond={patologia}"
            r = requests.get(url)
            r.raise_for_status()
            return len(ET.fromstring(r.content).findall(".//item"))
        except:
            return 0

    return jsonify({
        mol1: contar(mol1),
        mol2: contar(mol2),
        "patologia": patologia
    })

# -------------------- ENDPOINT ANALYSIS --------------------
@app.route('/analisis_endpoint', methods=['GET'])
def analisis_endpoint():
    patologia = request.args.get('patologia')
    fase = request.args.get('fase', '')
    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

    comunes = {
        "cáncer": ["supervivencia global", "respuesta objetiva"],
        "diabetes": ["HbA1c", "peso corporal"],
        "vitiligo": ["re-pigmentación", "mejora de VASI"]
    }

    return jsonify({
        "patologia": patologia,
        "fase": fase,
        "endpoints_comunes": comunes.get(patologia.lower(), ["No especificados"])
    })

# -------------------- PICO SUGERIDO (+ PDF) --------------------
@app.route('/pico_sugerido', methods=['GET'])
def pico_sugerido():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia')
    formato = request.args.get('formato', 'json')

    if not molecula or not patologia:
        return jsonify({"error": "Los parámetros 'molecula' y 'patologia' son obligatorios"}), 400

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

        return Response(buffer, mimetype='application/pdf', headers={
            "Content-Disposition": f"attachment;filename=pico_{molecula}.pdf"
        })

    return jsonify(pico)

# -------------------- TENDENCIAS DE INVESTIGACIÓN --------------------
@app.route('/tendencias_investigacion', methods=['GET'])
def tendencias_investigacion():
    patologia = request.args.get('patologia')
    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

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
        return jsonify({"error": f"No hay datos simulados para {patologia}"}), 404

    return jsonify({"patologia": patologia, **datos[patologia.lower()]})

# -------------------- RESUMEN CLÍNICO DE MOLÉCULA --------------------
@app.route('/resumen_molecula', methods=['GET'])
def resumen_molecula():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia')

    if not molecula or not patologia:
        return jsonify({"error": "Los parámetros 'molecula' y 'patologia' son obligatorios"}), 400

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

        return jsonify({
            "molécula": molecula,
            "patología": patologia,
            "ensayos_encontrados": cantidad,
            "fases_detectadas": fases_unicas or ["No especificadas"],
            "centros_participantes_estimados": f"{min(5 + cantidad, 50)} (estimación)",
            "recomendación": recomendacion,
            "observaciones": "Resumen automático. Requiere evaluación experta."
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# -------------------- EJECUCIÓN APP --------------------
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
