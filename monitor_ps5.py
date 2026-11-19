import os
import requests

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
PRECO_ALVO = 3999.99

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown"
    }
    requests.post(url, json=payload, timeout=10)

def verificar_preco():
    url = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "q": "PlayStation 5 Slim leitor disco 1TB",
        "condition": "new",
        "sort": "price_asc",
        "limit": 10
    }
    
    resp = requests.get(url, params=params, timeout=15)
    resultados = resp.json().get("results", [])

    for item in resultados:
        titulo = item.get("title", "").lower()
        preco = float(item.get("price", 99999))
        link = item.get("permalink", "")

        if (
            preco <= PRECO_ALVO
            and preco >= 2500
            and ("slim" in titulo)
            and ("leitor" in titulo or "disk" in titulo or "disco" in titulo)
            and ("digital" not in titulo)
        ):
            msg = (
                f"🚨 *ALERTA DE PREÇO PS5 SLIM COM LEITOR!*\n\n"
                f"📦 *Anúncio:* {item.get('title')}\n"
                f"💰 *Preço:* R$ {preco:,.2f}\n"
                f"🔗 [Abrir oferta]({link})"
            )
            enviar_telegram(msg)

if __name__ == "__main__":
    verificar_preco()
