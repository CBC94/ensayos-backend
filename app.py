from flask import Flask, request, jsonify
import requests
import xml.etree.ElementTree as ET
import os

app = Flask(__name__)

@app.route('/buscar_ensayos', methods=['GET'])
def buscar_ensayos():
    molecula = request.args.get('molecula')
    patologia = request.args.get('patologia', '')

    if not molecula:
        return jsonify({"error": "El parámetro 'molecula' es obligatorio"}), 400

    rss_url = f"https://clinicaltrials.gov/ct2/results/rss.xml?term={molecula}&cond={patologia}"

    try:
        response = requests.get(rss_url)
        response.raise_for_status()
        root = ET.fromstring(response.content)

        ensayos = []
        for item in root.findall(".//item"):
            titulo = item.find("title").text if item.find("title") is not None else ""
            link = item.find("link").text if item.find("link") is not None else ""
            ensayo_id = link.split("/")[-1] if link else "N/A"

            ensayos.append({
                "identificador": ensayo_id,
                "titulo": titulo,
                "estado": "En curso",
                "ubicacion": "Desconocida"
            })

        return jsonify({"ensayos": ensayos})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
