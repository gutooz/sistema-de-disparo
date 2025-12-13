import os
import time
import random
import threading
import pandas as pd
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

# =========================
# VARIÁVEIS DE AMBIENTE
# =========================
INSTANCE_ID = os.getenv("INSTANCE_ID")
TOKEN = os.getenv("TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN = os.getenv("ADMIN")

# =========================
# CONFIGURAÇÕES
# =========================
ARQUIVO_CONTATOS = "conversas_whatsapp_unificadas.xlsx"
TEMPO_MIN = 20
TEMPO_MAX = 22

mensagem_base = None
disparo_ativo = False

app = Flask(__name__)
client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# FUNÇÕES AUXILIARES
# =========================

def enviar_texto(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    headers = {
        "Client-Token": CLIENT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {
        "phone": numero,
        "message": mensagem
    }
    return requests.post(url, json=payload, headers=headers)


def gerar_variacao(mensagem):
    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": "Reescreva a mensagem de forma natural, curta, promocional e diferente."
            },
            {
                "role": "user",
                "content": mensagem
            }
        ]
    )
    return resposta.choices[0].message.content.strip()


def executar_disparo():
    global disparo_ativo

    while disparo_ativo:
        df = pd.read_csv(ARQUIVO_CONTATOS)

        pendentes = df[df["enviado"] == 0]

        if pendentes.empty:
            disparo_ativo = False
            break

        contato = pendentes.sample(1).iloc[0]
        numero = contato["numero"]

        mensagem_final = gerar_variacao(mensagem_base)
        enviar_texto(numero, mensagem_final)

        df.loc[df["numero"] == numero, "enviado"] = 1
        df.to_csv(ARQUIVO_CONTATOS, index=False)

        time.sleep(random.randint(TEMPO_MIN, TEMPO_MAX))


# =========================
# WEBHOOK Z-API
# =========================

@app.route("/webhook", methods=["POST"])
def webhook():
    global mensagem_base, disparo_ativo

    data = request.json
    numero = data.get("phone")
    texto = data.get("text", {}).get("message", "").lower()

    if numero != ADMIN:
        return jsonify({"status": "ignorado"})

    if texto.startswith("/mensagem"):
        mensagem_base = texto.replace("/mensagem", "").strip()
        return jsonify({"status": "mensagem definida"})

    if texto == "/enviar":
        if not mensagem_base:
            return jsonify({"erro": "mensagem não definida"})
        if not disparo_ativo:
            disparo_ativo = True
            threading.Thread(target=executar_disparo, daemon=True).start()
        return jsonify({"status": "disparo iniciado"})

    if texto == "/parar":
        disparo_ativo = False
        return jsonify({"status": "disparo pausado"})

    return jsonify({"status": "ok"})


@app.route("/")
def home():
    return "Disparo WhatsApp ativo"
