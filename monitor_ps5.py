from datetime import datetime, timezone, timedelta
import os
import smtplib
from email.mime.text import MIMEText
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_DESTINO = "marcusvaz.df@gmail.com"
EVENTO_GITHUB = os.environ.get("GITHUB_EVENT_NAME", "")

# Horário atual em Brasília (UTC-3)
FUSO_BR = timezone(timedelta(hours=-3))
AGORA_BR = datetime.now(FUSO_BR)

PRODUTOS = [
    {
        "nome": "PS5 Slim com Leitor 1TB",
        "query": "PlayStation 5 Slim leitor disco 1TB",
        "preco_min": 2500.00,
        "preco_alvo": 3999.99,
        "apenas_frete_gratis": False,
        "obrigatorias": ["slim"],
        "alguma_de": ["leitor", "disk", "disco"],
        "proibidas": ["digital"],
    },
    {
        "nome": "LG Dual Inverter Compact 9000 BTUs",
        "query": "Ar Condicionado LG Dual Inverter Compact 9000 BTU",
        "preco_min": 1300.00,
        "preco_alvo": 1899.99,
        "apenas_frete_gratis": True,
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

def analisar_produto(produto):
    url = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "q": produto["query"],
        "condition": "new",
        "sort": "price_asc",
        "limit": 30,
    }

    resp = requests.get(url, params=params, timeout=15)
    resultados = resp.json().get("results", [])

    ofertas_validas = []

    for item in resultados:
        titulo = item.get("title", "").lower()
        preco = float(item.get("price", 99999))
        link = item.get("permalink", "")
        frete_gratis = item.get("shipping", {}).get("free_shipping", False)

        if preco < produto["preco_min"]:
            continue

        if produto.get("apenas_frete_gratis") and not frete_gratis:
            continue

        if not all(p in titulo for p in produto["obrigatorias"]):
            continue

        if produto["alguma_de"] and not any(p in titulo for p in produto["alguma_de"]):
            continue

        if any(p in titulo for p in produto["proibidas"]):
            continue

        ofertas_validas.append({
            "titulo": item.get("title"),
            "preco": preco,
            "link": link,
            "frete_gratis": frete_gratis,
        })

    # Garante ordenação do menor para o maior preço
    ofertas_validas.sort(key=lambda x: x["preco"])
    return ofertas_validas

if __name__ == "__main__":
    blocos_email_urgente = []
    resumo_status = []

    # Envia resumo mesmo sem atingir a meta se você rodar manualmente OU às 09h e 20h (Brasília)
    enviar_status_periodico = (
        EVENTO_GITHUB == "workflow_dispatch"
        or (AGORA_BR.hour in (9, 20) and AGORA_BR.minute < 10)
    )

    for prod in PRODUTOS:
        ofertas = analisar_produto(prod)
        alvo = prod["preco_alvo"]

        if not ofertas:
            resumo_status.append(
                f"• *{prod['nome']}:* Nenhum anúncio válido encontrado com os filtros atuais."
            )
            continue

        menor = ofertas[0]
        diferenca = menor["preco"] - alvo
        sinal = "+" if diferenca > 0 else "-"
        diff_formatada = f"{sinal} {formatar_reais(abs(diferenca))}"
        status_frete = "Grátis" if menor["frete_gratis"] else "Verificar no anúncio"

        if diferenca <= 0:
            # META ATINGIDA OU SUPERADA (diferença negativa ou zero)
            msg_tg = (
                f"🚨 *META ATINGIDA: {prod['nome']}*\n\n"
                f"📦 *Anúncio:* {menor['titulo']}\n"
                f"💰 *Menor preço atual:* {formatar_reais(menor['preco'])}\n"
                f"🎯 *Seu alvo:* {formatar_reais(alvo)}\n"
                f"📉 *Diferença:* *{diff_formatada}* (abaixo do alvo!)\n"
                f"🚚 *Frete:* {status_frete}\n"
                f"🔗 [Abrir oferta agora]({menor['link']})"
            )
            enviar_telegram(msg_tg)

            blocos_email_urgente.append(
                f"========================================\n"
                f"META ATINGIDA: {prod['nome']}\n"
                f"Anúncio: {menor['titulo']}\n"
                f"Menor preço atual: {formatar_reais(menor['preco'])}\n"
                f"Seu alvo: {formatar_reais(alvo)}\n"
                f"Diferença: {diff_formatada}\n"
                f"Frete: {status_frete}\n"
                f"Link: {menor['link']}\n"
            )
        else:
            # AINDA ACIMA DO ALVO (diferença positiva)
            resumo_status.append(
                f"• *{prod['nome']}*\n"
                f"  Menor atual: *{formatar_reais(menor['preco'])}* | Alvo: {formatar_reais(alvo)}\n"
                f"  Diferença: *{diff_formatada}* (acima do alvo)\n"
                f"  🔗 [Ver menor anúncio]({menor['link']})"
            )

    # Dispara o e-mail consolidado se algum item atingiu a meta
    if blocos_email_urgente:
        qtd = len(blocos_email_urgente)
        enviar_email(
            f"🚨 Meta Atingida: {qtd} {'produto' if qtd == 1 else 'produtos'} no alvo!",
            "O robô encontrou oferta(s) no seu preço alvo ou abaixo:\n\n" + "\n".join(blocos_email_urgente),
        )

    # Envia o boletim de acompanhamento no Telegram (nos disparos manuais ou às 09h e 20h)
    if enviar_status_periodico and resumo_status:
        msg_boletim = (
            f"📊 *Boletim de Preços ({AGORA_BR.strftime('%H:%M')})*\n\n"
            + "\n\n".join(resumo_status)
        )
        enviar_telegram(msg_boletim)
