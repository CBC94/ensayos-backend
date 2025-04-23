from flask import Flask, request, jsonify, Response
import requests
import xml.etree.ElementTree as ET
import os
import csv
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

app = Flask(__name__)

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
            resumen = f"Se encontraron {len(ensayos)} ensayos clínicos con la molécula \"{molecula}\""
            if patologia:
                resumen += f" y la patología \"{patologia}\""
            if filtro_estado:
                resumen += f", con estado \"{filtro_estado}\""
            if filtro_fase:
                resumen += f", en fase \"{filtro_fase}\""
            if filtro_pais:
                resumen += f", en el país \"{filtro_pais}\""
            resumen += ":\n\n"

            for i, ensayo in enumerate(ensayos[:10], 1):
                resumen += f"{i}. {ensayo['titulo']} (ID: {ensayo['identificador']})\n"

            return resumen, 200, {'Content-Type': 'text/plain; charset=utf-8'}

        return jsonify({"ensayos": ensayos})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

        titulo = get_text(".//official_title") or get_text(".//brief_title")
        resumen = get_text(".//brief_summary/textblock")
        estado = get_text(".//overall_status")
        fase = get_text(".//phase")
        tipo_estudio = get_text(".//study_type")
        patrocinador = get_text(".//lead_sponsor/agency")
        fecha_inicio = get_text(".//start_date")
        criterios = get_text(".//eligibility/criteria/textblock")
        intervenciones = [el.text for el in root.findall(".//intervention/intervention_name")]
        condiciones = [el.text for el in root.findall(".//condition")]
        ubicaciones = [el.text for el in root.findall(".//location/facility/name")]

        return jsonify({
            "id": ensayo_id,
            "titulo": titulo,
            "resumen": resumen,
            "estado": estado,
            "fase": fase,
            "tipo_estudio": tipo_estudio,
            "patrocinador": patrocinador,
            "fecha_inicio": fecha_inicio,
            "condiciones": condiciones,
            "intervenciones": intervenciones,
            "ubicaciones": ubicaciones,
            "criterios": criterios
        })

    except Exception as e:
        return jsonify({"error": f"No se pudo obtener el detalle del ensayo: {str(e)}"}), 500


@app.route('/exportar_ensayos', methods=['GET'])
def exportar_ensayos():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia', '')

    if not molecula:
        return jsonify({"error": "El parámetro 'molecula' es obligatorio"}), 400

    rss_url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"

    try:
        response = requests.get(rss_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['identificador', 'titulo', 'estado', 'fase', 'ubicacion'])

        for item in root.findall(".//item"):
            titulo = item.find("title").text or ""
            link = item.find("link").text or ""
            ensayo_id = link.split("/")[-1] if link else "N/A"
            estado = "En curso"
            fase = "3" if "phase 3" in titulo.lower() else "Desconocida"
            ubicacion = "Desconocida"

            writer.writerow([ensayo_id, titulo, estado, fase, ubicacion])

        output.seek(0)
        return Response(
            output,
            mimetype='text/csv',
            headers={"Content-Disposition": f"attachment;filename=ensayos_{molecula}.csv"}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/exportar_ensayos_pdf', methods=['GET'])
def exportar_ensayos_pdf():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia', '')

    if not molecula:
        return jsonify({"error": "El parámetro 'molecula' es obligatorio"}), 400

    rss_url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"

    try:
        response = requests.get(rss_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, height - 50, f"Ensayos clínicos - {molecula} / {patologia}")
        c.setFont("Helvetica", 10)

        y = height - 80
        for i, item in enumerate(root.findall(".//item")[:20], 1):
            titulo = item.find("title").text or ""
            link = item.find("link").text or ""
            ensayo_id = link.split("/")[-1] if link else "N/A"

            if y < 60:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 50

            c.drawString(50, y, f"{i}. {titulo} (ID: {ensayo_id})")
            y -= 20

        c.save()
        buffer.seek(0)

        return Response(
            buffer,
            mimetype='application/pdf',
            headers={"Content-Disposition": f"attachment;filename=ensayos_{molecula}.pdf"}
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/comparar_moleculas', methods=['GET'])
def comparar_moleculas():
    molecula1 = request.args.get('molecula1')
    molecula2 = request.args.get('molecula2')
    patologia = request.args.get('patologia')

    if not molecula1 or not molecula2 or not patologia:
        return jsonify({"error": "Los parámetros 'molecula1', 'molecula2' y 'patologia' son obligatorios"}), 400

    def contar_ensayos(molecula):
        url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            return len(root.findall(".//item"))
        except:
            return 0

    return jsonify({
        molecula1: contar_ensayos(molecula1),
        molecula2: contar_ensayos(molecula2),
        "patologia": patologia
    })


@app.route('/analisis_endpoint', methods=['GET'])
def analisis_endpoint():
    patologia = request.args.get('patologia')
    fase = request.args.get('fase', '')

    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

    endpoints = {
        "cáncer": ["supervivencia global", "respuesta objetiva"],
        "diabetes": ["control glucémico", "HbA1c"],
        "vitiligo": ["re-pigmentación", "mejora clínica"]
    }

    return jsonify({
        "patologia": patologia,
        "fase": fase,
        "endpoints_comunes": endpoints.get(patologia.lower(), ["Endpoint no determinado"])
    })


@app.route('/pico_sugerido', methods=['GET'])
def pico_sugerido():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia')

    if not molecula or not patologia:
        return jsonify({"error": "Los parámetros 'molecula' y 'patologia' son obligatorios"}), 400

    pico = {
        "Paciente": f"Pacientes con {patologia}",
        "Intervención": f"{molecula}",
        "Comparador": "Placebo o tratamiento estándar",
        "Outcome": "Mejora clínica o endpoint primario"
    }

    return jsonify(pico)


@app.route('/nuevos_ensayos', methods=['GET'])
def nuevos_ensayos():
    patologia = request.args.get('patologia', '')

    url = f"https://clinicaltrials.gov/ct2/results/rss.xml?cond={patologia}"

    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        items = root.findall(".//item")[:5]

        resultados = [{
            "titulo": item.find("title").text,
            "link": item.find("link").text
        } for item in items]

        return jsonify({"nuevos_ensayos": resultados})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/top_centros', methods=['GET'])
def top_centros():
    patologia = request.args.get('patologia')
    pais = request.args.get('pais', '').lower()

    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

    centros = [
        {"nombre": "Hospital Clínico Central", "pais": "españa", "ensayos": 15},
        {"nombre": "Centro de Investigación Avanzada", "pais": "mexico", "ensayos": 12},
        {"nombre": "Instituto de Salud Global", "pais": "argentina", "ensayos": 10}
    ]

    if pais:
        centros = [c for c in centros if pais in c["pais"].lower()]

    return jsonify({"centros_activos": centros})


@app.route('/cambios_estado_recientes', methods=['GET'])
def cambios_estado_recientes():
    patologia = request.args.get('patologia', '')
    dias = int(request.args.get('dias', 30))

    cambios = [
        {"id": "NCT001", "estado_anterior": "Reclutando", "estado_actual": "Completado", "dias": 10},
        {"id": "NCT002", "estado_anterior": "Activo", "estado_actual": "Retirado", "dias": 5},
        {"id": "NCT003", "estado_anterior": "Planificado", "estado_actual": "Reclutando", "dias": 20}
    ]

    filtrados = [c for c in cambios if c["dias"] <= dias]
    return jsonify({"cambios_recientes": filtrados})


@app.route('/mecanismos_accion', methods=['GET'])
def mecanismos_accion():
    patologia = request.args.get('patologia')

    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

    mecanismos = {
        "cáncer": ["Inhibición de tirosina quinasa", "Inmunoterapia"],
        "diabetes": ["Sensibilización a insulina", "Estimulación pancreática"],
        "vitiligo": ["Inhibidores JAK", "Modulación inmune"]
    }

    return jsonify({
        "patologia": patologia,
        "mecanismos": mecanismos.get(patologia.lower(), ["No disponible"])
    })


@app.route('/mapa_investigacion', methods=['GET'])
def mapa_investigacion():
    patologia = request.args.get('patologia')

    if not patologia:
        return jsonify({"error": "El parámetro 'patologia' es obligatorio"}), 400

    mapa = {
        "cáncer": {"EEUU": 120, "España": 80},
        "diabetes": {"México": 50, "Argentina": 40},
        "vitiligo": {"EEUU": 10, "India": 8}
    }

    return jsonify({
        "patologia": patologia,
        "distribucion_geografica": mapa.get(patologia.lower(), {})
    })


@app.route('/moleculas_por_fase', methods=['GET'])
def moleculas_por_fase():
    fase = request.args.get('fase')
    patologia = request.args.get('patologia', '')

    if not fase:
        return jsonify({"error": "El parámetro 'fase' es obligatorio"}), 400

    fases = {
        "fase 1": ["Molécula A", "Molécula B"],
        "fase 2": ["Molécula C", "Molécula D"],
        "fase 3": ["Molécula E", "Molécula F"]
    }

    return jsonify({
        "fase": fase,
        "patologia": patologia,
        "moleculas": fases.get(fase.lower(), [])
    })


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
