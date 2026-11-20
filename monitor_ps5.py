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
EVENTO_GITHUB = os.environ.get("GITHUB_EVENT_NAME", "")

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

PRODUTOS = [
    {
        "nome": "PS5 Slim com Leitor 1TB",
        "query": "PlayStation 5 Slim 1TB com Leitor",
        "preco_min": 2800.00,
        "preco_alvo": 3999.99,
        "obrigatorias": ["slim"],
        "alguma_de": ["leitor", "disk", "disco", "1tb"],
        "proibidas": ["digital", "controle", "dualsense", "cabo", "suporte", "capa", "jogo"],
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

def extrair_produtos_json(obj, encontrados):
    if isinstance(obj, dict):
        nome = obj.get("name") or obj.get("title") or ""
        preco = None
        link = obj.get("url") or obj.get("link") or ""

        if "price" in obj and isinstance(obj["price"], (int, float, str)):
            try:
                preco = float(str(obj["price"]).replace(",", "."))
            except ValueError:
                pass
        elif "lowPrice" in obj:
            try:
                preco = float(str(obj["lowPrice"]).replace(",", "."))
            except ValueError:
                pass
        elif isinstance(obj.get("offers"), dict):
            val = obj["offers"].get("lowPrice") or obj["offers"].get("price")
            if val is not None:
                try:
                    preco = float(str(val).replace(",", "."))
                except ValueError:
                    pass

        if nome and preco and preco > 0:
            if link and link.startswith("/"):
                link = f"https://www.buscape.com.br{link}"
            encontrados.append({"titulo": str(nome).strip(), "preco": preco, "link": link})

        for v in obj.values():
            extrair_produtos_json(v, encontrados)
    elif isinstance(obj, list):
        for item in obj:
            extrair_produtos_json(item, encontrados)

def analisar_produto(produto):
    q_encoded = urllib.parse.quote(produto["query"])
    url = f"https://www.buscape.com.br/search?q={q_encoded}"

    resp = requests.get(url, headers=HEADERS, timeout=20)
    if resp.status_code != 200:
        return [], f"Erro HTTP {resp.status_code} ao consultar Buscapé"

    html = resp.text
    brutos = []

    match_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match_next:
        try:
            dados = json.loads(match_next.group(1))
            extrair_produtos_json(dados, brutos)
        except json.JSONDecodeError:
            pass

    for match_ld in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            dados_ld = json.loads(match_ld)
            extrair_produtos_json(dados_ld, brutos)
        except json.JSONDecodeError:
            pass

    ofertas_validas = []
    vistos = set()

    for item in brutos:
        titulo_orig = item["titulo"]
        titulo = titulo_orig.lower()
        preco = item["preco"]
        link = item["link"] or url

        if preco < produto["preco_min"]:
            continue

        if not all(p in titulo for p in produto["obrigatorias"]):
            continue

        if produto["alguma_de"] and not any(p in titulo for p in produto["alguma_de"]):
            continue

        if any(p in titulo for p in produto["proibidas"]):
            continue

        chave = (titulo_orig, preco)
        if chave in vistos:
            continue
        vistos.add(chave)

        ofertas_validas.append({
            "titulo": titulo_orig,
            "preco": preco,
            "link": link,
        })

    ofertas_validas.sort(key=lambda x: x["preco"])
    return ofertas_validas, None

if __name__ == "__main__":
    blocos_email_urgente = []
    resumo_status = []

    chave_hora_atual = AGORA_BR.strftime("%Y-%m-%d-%H")
    ultimo_enviado = ler_ultimo_boletim()

    # Janela das 06h até as 00h (inclusive)
    dentro_janela_boletim = (6 <= AGORA_BR.hour <= 23) or (AGORA_BR.hour == 0)
    enviar_status_periodico = (
        EVENTO_GITHUB == "workflow_dispatch"
        or (dentro_janela_boletim and chave_hora_atual != ultimo_enviado)
    )

    for prod in PRODUTOS:
        ofertas, erro = analisar_produto(prod)
        alvo = prod["preco_alvo"]

        if erro:
            resumo_status.append(f"• *{prod['nome']}:* {erro}")
            continue

        if not ofertas:
            resumo_status.append(
                f"• *{prod['nome']}:* Nenhum anúncio válido encontrado com os filtros atuais."
            )
            continue

        menor = ofertas[0]
        diferenca = menor["preco"] - alvo
        sinal = "+" if diferenca > 0 else "-"
        diff_formatada = f"{sinal} {formatar_reais(abs(diferenca))}"

        if diferenca <= 0:
            msg_tg = (
                f"🚨 *META ATINGIDA: {prod['nome']}*\n\n"
                f"📦 *Anúncio:* {menor['titulo']}\n"
                f"💰 *Menor preço atual:* {formatar_reais(menor['preco'])}\n"
                f"🎯 *Seu alvo:* {formatar_reais(alvo)}\n"
                f"📉 *Diferença:* *{diff_formatada}* (abaixo do alvo!)\n"
                f"🔗 [Ver lojas e ofertas]({menor['link']})"
            )
            enviar_telegram(msg_tg)

            blocos_email_urgente.append(
                f"========================================\n"
                f"META ATINGIDA: {prod['nome']}\n"
                f"Anúncio: {menor['titulo']}\n"
                f"Menor preço atual: {formatar_reais(menor['preco'])}\n"
                f"Seu alvo: {formatar_reais(alvo)}\n"
                f"Diferença: {diff_formatada}\n"
                f"Link: {menor['link']}\n"
            )
        else:
            resumo_status.append(
                f"• *{prod['nome']}*\n"
                f"  Menor atual: *{formatar_reais(menor['preco'])}* | Alvo: {formatar_reais(alvo)}\n"
                f"  Diferença: *{diff_formatada}* (acima do alvo)\n"
                f"  🔗 [Ver menor preço]({menor['link']})"
            )

    if blocos_email_urgente:
        qtd = len(blocos_email_urgente)
        enviar_email(
            f"🚨 Meta Atingida: {qtd} {'produto' if qtd == 1 else 'produtos'} no alvo!",
            "O robô encontrou oferta(s) no seu preço alvo ou abaixo:\n\n" + "\n".join(blocos_email_urgente),
        )

    if enviar_status_periodico and resumo_status:
        msg_boletim = (
            f"📊 *Boletim de Preços ({AGORA_BR.strftime('%H:%M')})*\n\n"
            + "\n\n".join(resumo_status)
        )
        enviar_telegram(msg_boletim)
        salvar_ultimo_boletim(chave_hora_atual)
