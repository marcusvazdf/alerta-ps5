import os
import json
import hashlib
from curl_cffi import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
STATE_FILE = "sent_alerts.json"

# Configuração das buscas e tetos de preço (ajuste conforme sua meta)
TARGETS = [
    {
        "name": "Leitor de Disco PS5 Slim (CFI-2000)",
        "query": "leitor de disco ps5 slim sony",
        "max_price": 620.00,
        "min_price": 420.00,  # Evita capas, cabos e suportes baratos
        "must_include_any": ["leitor", "unidade de disco", "drive", "cfi-2000", "cfi-zdd1"],
        "must_exclude": ["base", "suporte", "capa", "cooler", "adesivo", "cabo", "usado", "defeito", "carcaca"]
    },
    {
        "name": "SSD NVMe 1TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 1tb pcie 4.0 ps5",
        "max_price": 650.00,
        "min_price": 380.00,  # Evita SSDs falsos ou só o dissipador avulso
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["500gb", "512gb", "256gb", "sata", "case", "adaptador", "usado", "dissipador apenas"]
    },
    {
        "name": "SSD NVMe 2TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 2tb pcie 4.0 ps5",
        "max_price": 1150.00,
        "min_price": 700.00,
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["1tb", "500gb", "sata", "case", "adaptador", "usado"]
    }
]


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Secrets do Telegram não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")


def is_valid_item(title, price, target):
    title_lower = title.lower()
    if not (target["min_price"] <= price <= target["max_price"]):
        return False
    if any(bad in title_lower for bad in target["must_exclude"]):
        return False
    if not any(good in title_lower for good in target["must_include_any"]):
        return False
    return True


def search_mercadolivre(target):
    url = "https://api.mercadolibre.com/sites/MLB/search"
    params = {
        "q": target["query"],
        "condition": "new",
        "sort": "price_asc",
        "limit": 30
    }
    try:
        resp = requests.get(
            url,
            params=params,
            impersonate="chrome124",
            timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        print(f"Erro na busca '{target['name']}': {e}")
        return []


def main():
    state = load_state()
    new_alerts = 0

    for target in TARGETS:
        results = search_mercadolivre(target)
        for item in results:
            title = item.get("title", "")
            price = float(item.get("price", 0))
            permalink = item.get("permalink", "")
            item_id = item.get("id", "")

            if not is_valid_item(title, price, target):
                continue

            # Gera chave única por anúncio + faixa de preço (arredondada a cada R$ 10)
            price_bucket = int(price // 10)
            alert_key = hashlib.md5(f"{item_id}_{price_bucket}".encode()).hexdigest()

            if alert_key in state:
                continue

            shipping_free = item.get("shipping", {}).get("free_shipping", False)
            frete_txt = "Frete Grátis" if shipping_free else "Verificar frete"

            msg = (
                f"🔥 <b>Oportunidade: {target['name']}</b>\n\n"
                f"📦 {title}\n"
                f"💰 <b>R$ {price:,.2f}</b> ({frete_txt})\n"
                f"🔗 <a href='{permalink}'>Abrir no Mercado Livre</a>"
            ).replace(",", "X").replace(".", ",").replace("X", ".")

            send_telegram(msg)
            state[alert_key] = {"title": title, "price": price}
            new_alerts += 1

    if new_alerts > 0:
        save_state(state)
    print(f"Execução concluída. Novos alertas enviados: {new_alerts}")


if __name__ == "__main__":
    main()
