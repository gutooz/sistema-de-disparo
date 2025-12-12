import os
import pandas as pd
import requests
import time
import random
import threading
from flask import Flask, request, jsonify
from openai import OpenAI

# =========================================
# VARIÁVEIS DE AMBIENTE (RENDER)
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
PLANILHA = "conversas_whatsapp_unificadas.xlsx"

TEXTO_ATUAL = None
DISPARO_ATIVO = False
DISPARO_PAUSADO = False

# =========================================
# FUNÇÕES DE PLANILHA
# =========================================

def carregar_planilha():
    if not os.path.exists(PLANILHA):
        df = pd.DataFrame(columns=["Telefone", "Nome", "Status"])
        df.to_excel(PLANILHA, index=False)
    return pd.read_excel(PLANILHA)

def salvar_planilha(df):
    df.to_excel(PLANILHA, index=False)

# =========================================
# Z-API
# =========================================

def enviar_texto(numero, mensagem):
    url = f"https://api.z-api.io/instances/{INSTANCE_ID}/token/{TOKEN}/send-text"
    headers = {
        "Client-Token": CLIENT_TOKEN,
        "Content-Type": "application/json"
    }
    payload = {"phone": numero, "message": mensagem}
    return requests.post(url, json=payload, headers=headers).json()

def gerar_variacao(mensagem):
    client = OpenAI(api_key=OPENAI_API_KEY)
    prompt = f"Crie uma variação natural mantendo o mesmo sentido: '{mensagem}'"

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return resposta.choices[0].message.content

# =========================================
# DISPARO
# =========================================

def executar_disparo():
    global DISPARO_ATIVO, DISPARO_PAUSADO

    DISPARO_ATIVO = True
    DISPARO_PAUSADO = False

    df = carregar_planilha()

    contatos = df[
        (df["Telefone"].astype(str).str.startswith("55")) &
        (~df["Telefone"].astype(str).str.contains("group", na=False)) &
        (df["Status"] != "ENVIADO")
    ]

    contatos = contatos.sample(frac=1).reset_index(drop=True)

    total = len(contatos)
    enviados = 0

    for _, row in contatos.iterrows():

        if DISPARO_PAUSADO:
            enviar_texto(ADMIN, "⏸ Disparo pausado.")
            break

        numero = str(row["Telefone"])
        nome = str(row["Nome"]) if pd.notna(row["Nome"]) else ""

        msg_base = TEXTO_ATUAL.replace("{nome}", nome)

        try:
            msg = gerar_variacao(msg_base)
        except:
            msg = msg_base

        enviar_texto(numero, msg)

        df.loc[df["Telefone"] == numero, "Status"] = "ENVIADO"
        salvar_planilha(df)

        enviados += 1
        enviar_texto(ADMIN, f"📤 Enviado {enviados}/{total}")

        time.sleep(random.randint(TEMPO_MIN, TEMPO_MAX))

    DISPARO_ATIVO = False

    if not DISPARO_PAUSADO:
        enviar_texto(ADMIN, "🔥 Disparo finalizado.")

# =========================================
# FLASK
# =========================================

app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
def webhook():
    global TEXTO_ATUAL, DISPARO_PAUSADO

    data = request.json
    numero = data.get("phone")

    texto = None
    if isinstance(data.get("text"), dict):
        texto = data["text"].get("message")
    elif isinstance(data.get("message"), str):
        texto = data["message"]

    # =====================================
    # SALVAR CONTATO AUTOMÁTICO
    # =====================================
    if numero and numero != ADMIN:
        df = carregar_planilha()
        if numero not in df["Telefone"].astype(str).values:
            nome = data.get("senderName", "")
            df.loc[len(df)] = [numero, nome, ""]
            salvar_planilha(df)

    # =====================================
    # COMANDOS ADMIN
    # =====================================
    if numero != ADMIN:
        return jsonify({"ok": True})

    if texto == "/ajuda":
        ajuda = (
            "📌 *COMANDOS DISPONÍVEIS*\n\n"
            "/mensagem <texto> → Define a mensagem do disparo\n"
            "/enviar → Inicia o disparo\n"
            "/pausar → Pausa o disparo\n"
            "/continuar → Continua de onde parou\n"
            "/status → Mostra o status atual\n"
            "/ajuda → Lista todos os comandos\n\n"
            "ℹ Use {nome} para personalizar a mensagem."
        )
        enviar_texto(ADMIN, ajuda)
        return jsonify({"ok": True})

    if texto.startswith("/mensagem"):
        TEXTO_ATUAL = texto.replace("/mensagem", "").strip()
        enviar_texto(ADMIN, "📝 Mensagem definida.")
        return jsonify({"ok": True})

    if texto == "/enviar":
        if not TEXTO_ATUAL:
            enviar_texto(ADMIN, "⚠ Defina a mensagem antes.")
            return jsonify({"ok": True})

        threading.Thread(target=executar_disparo, daemon=True).start()
        enviar_texto(ADMIN, "🚀 Disparo iniciado.")
        return jsonify({"ok": True})

    if texto == "/pausar":
        DISPARO_PAUSADO = True
        enviar_texto(ADMIN, "⏸ Pausando disparo...")
        return jsonify({"ok": True})

    if texto == "/continuar":
        if not DISPARO_ATIVO:
            threading.Thread(target=executar_disparo, daemon=True).start()
            enviar_texto(ADMIN, "▶ Retomando disparo.")
        return jsonify({"ok": True})

    if texto == "/status":
        status = (
            "⏸ Pausado" if DISPARO_PAUSADO
            else "▶ Rodando" if DISPARO_ATIVO
            else "⏹ Parado"
        )
        enviar_texto(ADMIN, f"📊 Status do disparo: {status}")
        return jsonify({"ok": True})

    return jsonify({"ok": True})

# =========================================
# START
# =========================================

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    print(f"🔥 Servidor rodando na porta {port}")
    app.run(host="0.0.0.0", port=port)
