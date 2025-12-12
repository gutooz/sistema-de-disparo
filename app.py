import os
import pandas as pd
import threading
import time
import random
import requests
from flask import Flask, request, jsonify

# ===============================
# CONFIGURAÇÕES
# ===============================

PLANILHA_PATH = "conversas_whatsapp_unificadas.xlsx"

INTERVALO_MIN = 15
INTERVALO_MAX = 20

INSTANCE_ID = os.getenv("INSTANCE_ID")
TOKEN = os.getenv("TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")
ADMIN = os.getenv("ADMIN")  # ex: 5511999999999

app = Flask(__name__)

# ===============================
# ESTADO GLOBAL
# ===============================

disparo_ativo = False
disparo_pausado = False
thread_disparo = None

# ===============================
# PLANILHA
# ===============================

def carregar_df():
    if not os.path.exists(PLANILHA_PATH):
        df = pd.DataFrame(columns=["numero", "nome", "status"])
        df.to_excel(PLANILHA_PATH, index=False)
        return df
    return pd.read_excel(PLANILHA_PATH, dtype=str)


def salvar_df(df):
    df.to_excel(PLANILHA_PATH, index=False)

# ===============================
# WHATSAPP
# ===============================

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
    requests.post(url, json=payload, headers=headers)

# ===============================
# DISPARO
# ===============================

def executar_disparo():
    global disparo_ativo, disparo_pausado

    while disparo_ativo:
        if disparo_pausado:
            time.sleep(5)
            continue

        df = carregar_df()
        pendentes = df[df["status"] != "enviado"]

        if pendentes.empty:
            disparo_ativo = False

            # 🔔 AVISA ADMIN QUE FINALIZOU
            enviar_texto(
                ADMIN,
                "✅ *Disparo finalizado!*\n\n"
                "Todos os contatos da planilha já receberam mensagem."
            )
            return

        contato = pendentes.sample(1).iloc[0]
        numero = contato["numero"]

        enviar_texto(
            numero,
            "🍕 Hoje é dia de pizza! Aproveita nossas promoções e chama a gente aqui 😍"
        )

        df.loc[df["numero"] == numero, "status"] = "enviado"
        salvar_df(df)

        time.sleep(random.randint(INTERVALO_MIN, INTERVALO_MAX))

# ===============================
# WEBHOOK
# ===============================

@app.route("/webhook", methods=["POST"])
def webhook():
    global disparo_ativo, disparo_pausado, thread_disparo

    data = request.json or {}

    numero = data.get("phone")
    nome = data.get("senderName", "")
    texto = data.get("text", "").strip().lower()

    if not numero:
        return jsonify({"ok": True})

    df = carregar_df()

    # Salva contato novo
    if numero not in df["numero"].values:
        df.loc[len(df)] = {
            "numero": numero,
            "nome": nome,
            "status": "novo"
        }
        salvar_df(df)

    # Apenas ADMIN pode usar comandos
    if numero != ADMIN:
        return jsonify({"ok": True})

    # ===============================
    # COMANDOS
    # ===============================

    if texto == "/ajuda":
        enviar_texto(
            numero,
            "📋 *Comandos disponíveis:*\n\n"
            "/iniciar – Inicia o disparo\n"
            "/pausar – Pausa o disparo\n"
            "/retomar – Retoma o disparo\n"
            "/status – Status atual\n"
            "/ajuda – Lista comandos"
        )

    elif texto == "/iniciar":
        if not disparo_ativo:
            disparo_ativo = True
            disparo_pausado = False
            thread_disparo = threading.Thread(target=executar_disparo, daemon=True)
            thread_disparo.start()
            enviar_texto(numero, "✅ Disparo iniciado.")
        else:
            enviar_texto(numero, "⚠️ O disparo já está ativo.")

    elif texto == "/pausar":
        disparo_pausado = True
        enviar_texto(numero, "⏸️ Disparo pausado.")

    elif texto == "/retomar":
        if disparo_ativo:
            disparo_pausado = False
            enviar_texto(numero, "▶️ Disparo retomado.")
        else:
            enviar_texto(numero, "⚠️ Nenhum disparo ativo.")

    elif texto == "/status":
        enviados = len(df[df["status"] == "enviado"])
        total = len(df)

        enviar_texto(
            numero,
            f"📊 *Status do Disparo*\n\n"
            f"Ativo: {'Sim' if disparo_ativo else 'Não'}\n"
            f"Pausado: {'Sim' if disparo_pausado else 'Não'}\n"
            f"Total contatos: {total}\n"
            f"Enviados: {enviados}"
        )

    return jsonify({"ok": True})

# ===============================
# HEALTH CHECK
# ===============================

@app.route("/", methods=["GET"])
def health():
    return "OK", 200

# ===============================
# START
# ===============================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
