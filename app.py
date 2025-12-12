import os
import pandas as pd
import requests
import time
import random
import threading
from flask import Flask, request, jsonify
from openai import OpenAI

# =========================================
# VARIÁVEIS DE AMBIENTE DO RAILWAY
# =========================================
INSTANCE_ID = os.getenv("INSTANCE_ID")
TOKEN = os.getenv("TOKEN")
CLIENT_TOKEN = os.getenv("CLIENT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN = os.getenv("ADMIN")

# =========================================
# CONFIGURAÇÕES
# =========================================
TEMPO_MIN = 20
TEMPO_MAX = 60
TEXTO_ATUAL = None


# =========================================
# FUNÇÕES DE ENVIO
# =========================================

def enviar_texto(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    headers = {"Client-Token": CLIENT_TOKEN, "Content-Type": "application/json"}
    payload = {"phone": numero, "message": mensagem}
    return requests.post(url, json=payload, headers=headers).json()


def gerar_variacao(mensagem):
    client = OpenAI(api_key=OPENAI_API_KEY)

    prompt = f"Crie uma variação natural, mantendo o mesmo sentido, deste texto: '{mensagem}'"

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return resposta.choices[0].message.content


# =========================================
# FUNÇÃO DE DISPARO — APENAS TEXTO
# =========================================

def executar_disparo():
    global TEXTO_ATUAL

    df = pd.read_excel("conversas_whatsapp_unificadas.xlsx")
    df = df[~df["Telefone"].astype(str).str.contains("group")]
    df = df[df["Telefone"].astype(str).str.startswith("55")]

    for _, row in df.iterrows():
        numero = str(row["Telefone"])
        nome = str(row["Nome"])

        msg_base = TEXTO_ATUAL.replace("{nome}", nome)

        try:
            msg_variada = gerar_variacao(msg_base)
        except:
            msg_variada = msg_base

        print(f"\n➡️ Enviando para {numero} ({nome})")
        resposta = enviar_texto(numero, msg_variada)
        print("📨 Retorno:", resposta)

        tempo = random.randint(TEMPO_MIN, TEMPO_MAX)
        print(f"⏳ Aguardando {tempo} segundos...")
        time.sleep(tempo)

    enviar_texto(ADMIN, "🔥 Disparo finalizado!")


# =========================================
# FLASK — COMANDOS
# =========================================

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    global TEXTO_ATUAL

    data = request.json
    print("\n🟦 NOVA MENSAGEM RECEBIDA:")
    print(data)

    numero = data.get("phone")

    if numero != ADMIN:
        return jsonify({"status": "ignorado"}), 200

    # Ler mensagem
    texto = None
    if isinstance(data.get("text"), dict):
        texto = data["text"].get("message")
    elif isinstance(data.get("message"), str):
        texto = data["message"]

    # /mensagem
    if texto and texto.startswith("/mensagem"):
        TEXTO_ATUAL = texto.replace("/mensagem", "").strip()
        enviar_texto(ADMIN, f"📝 Mensagem definida:\n{TEXTO_ATUAL}")
        return jsonify({"ok": True})

    # /enviar
    if texto and texto.startswith("/enviar"):

        if not TEXTO_ATUAL:
            enviar_texto(ADMIN, "⚠ Defina uma mensagem com /mensagem primeiro.")
            return jsonify({"erro": True})

        enviar_texto(ADMIN, "🚀 Iniciando disparo somente texto...")

        threading.Thread(
            target=executar_disparo,
            daemon=True
        ).start()

        return jsonify({"ok": True})

    return jsonify({"status": "ok"})


# =========================================
# START SERVER — PORTA DO RAILWAY
# =========================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🔥 SERVIDOR RODANDO NA PORTA {port}")
    print("Comandos: /mensagem, /enviar")
    app.run(host="0.0.0.0", port=port)