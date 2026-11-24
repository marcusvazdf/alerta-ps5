from datetime import datetime, timezone, timedelta
import json
import os
import re
import smtplib
from email.mime.text import MIMEText
import urllib.parse
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_DESTINO = "marcusvaz.df@gmail.com"

FUSO_BR = timezone(timedelta(hours=-3))
AGORA_BR = datetime.now(FUSO_BR)
ARQUIVO_CONTROLE = "ultimo_boletim.txt"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}

FONTES = [
    ("Buscapé", "https://www.buscape.com.br"),
    ("Zoom", "https://www.zoom.com.br"),
]

PRODUTOS = [
    {
        "nome": "PS5 Slim com Leitor 1TB",
        "query": "PlayStation 5 Slim 1TB com Leitor",
        "preco_min": 2800.00,
        "preco_alvo": 3999.99,
        "obrigatorias": ["slim"],
        "alguma_de": ["leitor", "disk", "disco", "1tb"],
        "proibidas": ["digital", "controle", "dualsense", "cabo", "suporte", "capa", "jogo", "usado"],
    },
    {
        "nome": "PS5 Slim Digital 825GB/1TB",
        "query": "PlayStation 5 Slim Digital",
        "preco_min": 2600.00,
        "preco_alvo": 3550.00,
        "obrigatorias": ["slim", "digital"],
        "alguma_de": ["825gb", "1tb", "console", "playstation"],
        "proibidas": ["controle", "dualsense", "cabo", "suporte", "capa", "jogo", "usado"],
    },
    {
        "nome": "LG Dual Inverter Compact 9000 BTUs",
        "query": "Ar Condicionado LG Dual Inverter Compact 9000 BTUs",
        "preco_min": 1400.00,
        "preco_alvo": 1899.99,
        "obrigatorias": ["lg", "9000", "compact"],
        "alguma_de": ["inverter", "dual"],
        "proibidas": [
            "usado", "placa", "controle", "evaporadora",
            "condensadora", "suporte", "12000", "18000", "24000"
        ],
    },
]

def formatar_reais(valor):
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def ler_ultimo_boletim():
    if os.path.exists(ARQUIVO_CONTROLE):
        with open(ARQUIVO_CONTROLE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return ""

def salvar_ultimo_boletim(chave_hora):
    with open(ARQUIVO_CONTROLE, "w", encoding="utf-8") as f:
        f.write(chave_hora)

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload, timeout=10)

def enviar_email(assunto, corpo):
    if not EMAIL_USER or not EMAIL_PASS:
        return
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_DESTINO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as servidor:
        servidor.login(EMAIL_USER, EMAIL_PASS)
        servidor.send_message(msg)

def extrair_produtos_json(obj, encontrados, base_url, nome_fonte):
    if isinstance(obj, dict):
        nome = obj.get("name") or obj.get("title") or ""
        preco = None
        link = obj.get("url") or obj.get("link") or ""
