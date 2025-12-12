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

COLUNAS_PADRAO = ["numero", "nome", "status"]

app = Flask(__name__)

# ===============================
# ESTADO GLOBAL
# ===============================

disparo_ativo = False
disparo_pausado = False
thread_disparo = None

# ===============================
# PLANILHA (BLINDADA)
# ===============================

def carregar_df():
    # Se não existir, cria corretamente
    if not os.path.exists(PLANILHA_PATH):
        df = pd.DataFrame(columns=COLUNAS_PADRAO)
        df.to_excel(PLANILHA_PATH, index=False)
        return df

    df = pd.read_excel(PLANILHA_PATH, dtype=str)

    # 🔐 GARANTE COLUNAS
    for coluna in COLUNAS_PADRAO:
        if coluna not in df.columns:
            df[coluna] = ""

    # Reordena e remove lixo
    df = df[COLUNAS_PADRAO]

    return df


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
    requests.post(url, json=payload, headers=headers, timeout=15)

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
# TEXTO SEGURO
# ===============================

def extrair_texto(data):
    texto = data.get("text", "")

    if isinstance(texto, dict):
        texto = texto.get("message", "")

    if isinstance(texto, str):
        return texto.strip().lower()

    return ""

# ===============================
# WEBHOOK
# ===============================

@app.route("/webhook", methods=["POST"])
def webhook():
    global disparo_ativo, disparo_pausado, thread_disparo

    data = request.json or {}

    numero = data.get("phone")
    nome = data.get("senderName", "")
    texto = extrair_texto(data)

    if not numero:
        return jsonify({"ok": True})

    df = carregar_df()

    # Salva contato novo (sem duplicar)
    if numero not in df["numero"].astype(str).values:
        df.loc[len(df)] = {
            "numero": numero,
            "nome": nome,
            "status": "novo"
        }
        salvar_df(df)

    # Apenas ADMIN pode usar comandos
    if numero != ADMIN:
        return jsonify({"ok": True})

    if texto == "/ajuda":
        enviar_texto(
            numero,
            "📋 *Comandos disponíveis:*\n\n"
            "/iniciar\n/pausar\n/retomar\n/status\n/ajuda"
        )

    elif texto == "/iniciar":
        if not disparo_ativo:
            disparo_ativo = True
            disparo_pausado = False
            thread_disparo = threading.Thread(target=executar_disparo, daemon=True)
            thread_disparo.start()
            enviar_texto(numero, "✅ Disparo iniciado.")

    elif texto == "/pausar":
        disparo_pausado = True
        enviar_texto(numero, "⏸️ Disparo pausado.")

    elif texto == "/retomar":
        disparo_pausado = False
        enviar_texto(numero, "▶️ Disparo retomado.")

    elif texto == "/status":
        enviar_texto(
            numero,
            f"📊 Status\nAtivo: {disparo_ativo}\nPausado: {disparo_pausado}\nTotal: {len(df)}"
        )

    return jsonify({"ok": True})

# ===============================
# HEALTH
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
