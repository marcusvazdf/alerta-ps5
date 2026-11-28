import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from curl_cffi import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GITHUB_EVENT_NAME = os.environ.get("GITHUB_EVENT_NAME", "")

STATE_FILE = "metas_alertadas.json"
MINIMA_FILE = "minima_diaria.json"
BOLETIM_FILE = "ultimo_boletim.txt"

TZ_BR = timezone(timedelta(hours=-3))

TARGETS = [
    {
        "id": "leitor_ps5",
        "name": "Leitor de Disco PS5 Slim (CFI-2000)",
        "query": "leitor de disco ps5 slim sony",
        "target_price": 620.00,
        "min_price": 420.00,
        "must_include_any": ["leitor", "unidade de disco", "drive", "cfi-2000", "cfi-zdd1"],
        "must_exclude": ["base", "suporte", "capa", "cooler", "adesivo", "cabo", "usado", "defeito", "carcaca"]
    },
    {
        "id": "ssd_1tb",
        "name": "SSD NVMe 1TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 1tb pcie 4.0 ps5",
        "target_price": 650.00,
        "min_price": 380.00,
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["500gb", "512gb", "256gb", "sata", "case", "adaptador", "usado", "dissipador apenas"]
    },
    {
        "id": "ssd_2tb",
        "name": "SSD NVMe 2TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 2tb pcie 4.0 ps5",
        "target_price": 1150.00,
        "min_price": 700.00,
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["1tb", "500gb", "sata", "case", "adaptador", "usado"]
    }
]


def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def send_telegram(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Secrets do Telegram não configurados.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")


def is_valid_item(title, price, target):
    title_lower = title.lower()
    if price < target["min_price"]:
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
        "limit": 40
    }
    try:
        resp = requests.get(
            url,
            params=params,
            impersonate="chrome124",
            timeout=20
        )
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception as e:
        print(f"Erro na busca '{target['name']}': {e}")
        return []


def main():
    now_br = datetime.now(TZ_BR)
    today_str = now_br.strftime("%Y-%m-%d")
    time_str = now_br.strftime("%H:%M")

    state = load_json(STATE_FILE)
    minima_data = load_json(MINIMA_FILE)
    if minima_data.get("date") != today_str:
        minima_data = {"date": today_str, "items": {}}

    boletim_lines = [f"📊 <b>Boletim de Preços ({now_br.strftime('%d/%m %H:%M')})</b>\n"]
    resumo_hash_input = ""
    best_prices = {}

    for target in TARGETS:
        results = search_mercadolivre(target)
        valid_items = []

        for item in results:
            title = item.get("title", "")
            price = float(item.get("price", 0))
            permalink = item.get("permalink", "")
            item_id = item.get("id", "")

            if not is_valid_item(title, price, target):
                continue

            valid_items.append((price, title, permalink, item_id, item))

            if price <= target["target_price"]:
                price_bucket = int(price // 10)
                alert_key = hashlib.md5(f"{item_id}_{price_bucket}".encode()).hexdigest()
                if alert_key not in state:
                    shipping_free = item.get("shipping", {}).get("free_shipping", False)
                    frete_txt = "Frete Grátis" if shipping_free else "Verificar frete"
                    alert_msg = (
                        f"🔥 <b>META ATINGIDA: {target['name']}</b>\n\n"
                        f"📦 {title}\n"
                        f"💰 <b>{fmt_brl(price)}</b> ({frete_txt})\n"
                        f"🎯 Alvo: {fmt_brl(target['target_price'])}\n"
                        f"🔗 <a href='{permalink}'>Abrir no Mercado Livre</a>"
                    )
                    send_telegram(alert_msg)
                    state[alert_key] = {"title": title, "price": price, "date": today_str}

        if not valid_items:
            boletim_lines.append(f"• <b>{target['name']}</b>\n  Sem anúncios válidos encontrados.\n")
            continue

        valid_items.sort(key=lambda x: x[0])
        best_price, best_title, best_link, _, _ = valid_items[0]
        best_prices[target["id"]] = best_price

        day_record = minima_data["items"].get(target["id"])
        if not day_record or best_price < day_record["price"]:
            day_record = {"price": best_price, "time": time_str}
            minima_data["items"][target["id"]] = day_record

        diff = best_price - target["target_price"]
        if diff <= 0:
            diff_txt = f"✅ <b>{fmt_brl(abs(diff))} abaixo do alvo!</b>"
        else:
            diff_txt = f"+ {fmt_brl(diff)} (acima do alvo)"

        boletim_lines.append(
            f"• <b>{target['name']}</b>\n"
            f"  Menor atual: <b>{fmt_brl(best_price)}</b> | Alvo: {fmt_brl(target['target_price'])}\n"
            f"  Diferença: {diff_txt}\n"
            f"  📉 Menor do dia: {fmt_brl(day_record['price'])} (às {day_record['time']})\n"
            f"  🔗 <a href='{best_link}'>Ver menor preço</a>\n"
        )
        resumo_hash_input += f"{target['id']}:{int(best_price)};"

    if "ssd_1tb" in best_prices and "ssd_2tb" in best_prices:
        p1 = best_prices["ssd_1tb"]
        p2 = best_prices["ssd_2tb"]
        veredito = (
            "Compensa ir direto no <b>2TB</b> (custo por TB menor)."
            if (p2 / 2) < p1
            else "Melhor custo por TB no <b>1TB</b>."
        )
        boletim_lines.append(
            f"⚖️ <b>Análise SSD 1TB vs 2TB:</b>\n"
            f"• 1TB: {fmt_brl(p1)} | 2TB: {fmt_brl(p2)} ({fmt_brl(p2/2)}/TB)\n"
            f"✅ Veredito: {veredito}"
        )

    save_json(STATE_FILE, state)
    save_json(MINIMA_FILE, minima_data)

    current_hash = hashlib.md5(resumo_hash_input.encode()).hexdigest()
    last_hash = ""
    if os.path.exists(BOLETIM_FILE):
        with open(BOLETIM_FILE, "r", encoding="utf-8") as f:
            last_hash = f.read().strip()

    if GITHUB_EVENT_NAME == "workflow_dispatch" or current_hash != last_hash:
        send_telegram("\n".join(boletim_lines))
        with open(BOLETIM_FILE, "w", encoding="utf-8") as f:
            f.write(current_hash)
        print("Boletim enviado com sucesso.")
    else:
        print("Preços inalterados; boletim suprimido para evitar repetição.")


if __name__ == "__main__":
    main()
