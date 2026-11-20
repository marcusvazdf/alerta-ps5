import os
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

PRODUTOS = [
    {
        "nome": "PS5 Slim com Leitor 1TB",
        "query": "PlayStation 5 Slim leitor disco 1TB",
        "preco_min": 2500.00,
        "preco_max": 3999.99,
        "apenas_frete_gratis": False,
        "obrigatorias": ["slim"],
        "alguma_de": ["leitor", "disk", "disco"],
        "proibidas": ["digital"],
    },
    {
        "nome": "LG Dual Inverter Compact 9000 BTUs",
        "query": "Ar Condicionado LG Dual Inverter Compact 9000 BTU",
        "preco_min": 1300.00,
        "preco_max": 1899.99,
        "apenas_frete_gratis": True,  # Ignora anúncios sem frete grátis para Brasília
        "obrigatorias": ["lg", "9000", "compact"],
        "alguma_de": ["inverter", "dual"],
        "proibidas": [
            "usado", "placa", "controle", "evaporadora",
            "condensadora", "suporte", "12000", "18000", "24000"
        ],
    },
]

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
    }
    requests.post(url, json=payload, timeout=10)

def verificar_produto(produto):
    url = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "q": produto["query"],
        "condition": "new",
        "sort": "price_asc",
        "limit": 15,
    }

    resp = requests.get(url, params=params, timeout=15)
    resultados = resp.json().get("results", [])

    for item in resultados:
        titulo = item.get("title", "").lower()
        preco = float(item.get("price", 99999))
        link = item.get("permalink", "")
        frete_gratis = item.get("shipping", {}).get("free_shipping", False)

        if not (produto["preco_min"] <= preco <= produto["preco_max"]):
            continue

        if produto.get("apenas_frete_gratis") and not frete_gratis:
            continue

        if not all(p in titulo for p in produto["obrigatorias"]):
            continue

        if produto["alguma_de"] and not any(p in titulo for p in produto["alguma_de"]):
            continue

        if any(p in titulo for p in produto["proibidas"]):
            continue

        status_frete = "Grátis ✅" if frete_gratis else "Verificar no anúncio"

        msg = (
            f"🚨 *ALERTA DE PREÇO: {produto['nome']}*\n\n"
            f"📦 *Anúncio:* {item.get('title')}\n"
            f"💰 *Preço:* R$ {preco:,.2f}\n"
            f"🚚 *Frete:* {status_frete}\n"
            f"🔗 [Abrir oferta]({link})"
        )
        enviar_telegram(msg)

if __name__ == "__main__":
    for prod in PRODUTOS:
        verificar_produto(prod)
