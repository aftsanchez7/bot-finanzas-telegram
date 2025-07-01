
import os
from flask import Flask, request
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from pytz import timezone
import re
import random
from word2number import w2n
import requests

# Config
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
BOT_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
CL_TZ = timezone("America/Santiago")

app = Flask(__name__)

# Google Sheets auth
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", scope)
client = gspread.authorize(creds)
sheet = client.open("Finanzas WhatsApp Bot").worksheet("Datos")

# Respuestas naturales
respuestas_registro = [
    "✅ Listo, anoté tu gasto en {categoria}. ¡Buen control! 💸",
    "📝 Registrado en {categoria}. ¡Sigue así!",
    "👌 Gasto en {categoria} guardado. ¡Vamos bien!",
    "✅ Anotado: {categoria}. ¡Gracias por avisar!"
]

respuestas_error = [
    "😕 No entendí bien. Intenta algo como: 'Gasté 2000 en comida'",
    "📌 Puedes decir cosas como: 'Me pagaron 50000' o 'Gasté 3 mil en transporte'",
    "🤔 No logré procesarlo. ¿Puedes intentarlo con otra frase?"
]

def obtener_fecha(msg):
    if "ayer" in msg:
        return (datetime.now(CL_TZ) - timedelta(days=1)).strftime("%Y-%m-%d")
    return datetime.now(CL_TZ).strftime("%Y-%m-%d")

def parsear_monto(texto):
    try:
        monto_textual = re.findall(r"(?:\b[a-z]+\b[\s]*){1,4}", texto.lower())
        for fragmento in monto_textual:
            try:
                return w2n.word_to_num(fragmento.strip())
            except:
                continue
        numeros = re.findall(r"\d{1,3}(?:[.,]?\d{3})*", texto)
        if numeros:
            return int(numeros[0].replace(".", "").replace(",", ""))
    except:
        return None
    return None

def es_registro(mensaje):
    return any(x in mensaje for x in ["gasté", "me pagaron", "ingresé", "recibí"])

def es_consulta(mensaje):
    return any(x in mensaje for x in ["cuánto", "resumen", "total"])

def detectar_categoria(mensaje):
    categorias = ["comida", "transporte", "salud", "ocio", "educación", "ropa", "hogar", "otros"]
    for cat in categorias:
        if cat in mensaje.lower():
            return cat.capitalize()
    return "Otros"

def detectar_tipo(mensaje):
    if any(x in mensaje for x in ["me pagaron", "ingresé", "recibí"]):
        return "Ingreso"
    return "Gasto"

def detectar_rango_fechas(mensaje):
    hoy = datetime.now(CL_TZ).date()
    if "semana" in mensaje:
        inicio = hoy - timedelta(days=hoy.weekday())
        fin = hoy
    elif "mes" in mensaje:
        inicio = hoy.replace(day=1)
        fin = hoy
    else:
        inicio = fin = hoy
    return inicio.strftime("%Y-%m-%d"), fin.strftime("%Y-%m-%d")

def procesar_registro(mensaje, usuario):
    monto = parsear_monto(mensaje)
    if not monto:
        return random.choice(respuestas_error)

    tipo = detectar_tipo(mensaje)
    categoria = detectar_categoria(mensaje)
    fecha = obtener_fecha(mensaje)

    fila = [fecha, tipo, monto, categoria, "", mensaje, usuario]
    sheet.append_row(fila)
    return random.choice(respuestas_registro).format(categoria=categoria)

def procesar_consulta(mensaje):
    inicio, fin = detectar_rango_fechas(mensaje)
    categoria = detectar_categoria(mensaje) if any(cat in mensaje for cat in ["comida", "transporte", "ocio", "salud"]) else None

    datos = sheet.get_all_records()
    total = 0
    for fila in datos:
        try:
            if fila["Tipo"].lower() == "gasto" and inicio <= fila["Fecha"] <= fin:
                if not categoria or fila["Categoría"].lower() == categoria.lower():
                    total += int(fila["Monto"])
        except:
            continue

    if categoria:
        return f"📊 Total de gastos en {categoria} entre {inicio} y {fin}: ${total}"
    else:
        return f"📊 Total de gastos entre {inicio} y {fin}: ${total}"

def enviar_mensaje(chat_id, texto):
    url = f"{BOT_URL}/sendMessage"
    requests.post(url, json={"chat_id": chat_id, "text": texto})

@app.route("/telegram", methods=["POST"])
def telegram():
    data = request.get_json()
    mensaje = data.get("message", {}).get("text", "").lower()
    chat_id = data.get("message", {}).get("chat", {}).get("id", "")

    if not mensaje or not chat_id:
        return "OK"

    if es_registro(mensaje):
        respuesta = procesar_registro(mensaje, chat_id)
    elif es_consulta(mensaje):
        respuesta = procesar_consulta(mensaje)
    else:
        respuesta = random.choice(respuestas_error)

    enviar_mensaje(chat_id, respuesta)
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
