import os
import re
import json
import hashlib
from urllib.parse import quote_plus
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
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
        "query": "leitor de disco ps5 slim",
        "target_price": 620.00,
        "min_price": 420.00,
        "must_include_any": ["leitor", "unidade de disco", "drive", "blu-ray", "cfi-2000", "cfi-zdd1"],
        "must_exclude": ["base", "suporte", "capa", "cooler", "adesivo", "cabo", "usado", "defeito", "carcaca", "console"]
    },
    {
        "id": "ssd_1tb",
        "name": "SSD NVMe 1TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 1tb pcie 4.0",
        "target_price": 650.00,
        "min_price": 380.00,
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["500gb", "512gb", "256gb", "2tb", "sata", "case", "adaptador", "usado", "dissipador apenas"]
    },
    {
        "id": "ssd_2tb",
        "name": "SSD NVMe 2TB PS5 (7000+ MB/s)",
        "query": "ssd nvme 2tb pcie 4.0",
        "target_price": 1150.00,
        "min_price": 700.00,
        "must_include_any": ["kc3000", "fury renegade", "s70 blade", "sn850", "980 pro", "990 pro", "mp600"],
        "must_exclude": ["1tb", "500gb", "sata", "case", "adaptador", "usado"]
    }
]


def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def parse_brl(text):
    if not text:
        return None
    cleaned = re.sub(r"[^\d,]", "", text).replace(".", "").replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


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
    if not price or price < target["min_price"]:
        return False
    title_lower = title.lower()
    if any(bad in title_lower for bad in target["must_exclude"]):
        return False
    if not any(good in title_lower for good in target["must_include_any"]):
        return False
    return True


def search_buscape(query):
    """Busca ofertas no Buscapé (agrega KaBuM, Amazon, ML, Magalu, etc.)"""
    url = f"https://www.buscape.com.br/search?q={quote_plus(query)}"
    items = []
    try:
        resp = requests.get(url, impersonate="chrome124", timeout=20)
        print(f"[Buscapé] '{query}' -> HTTP {resp.status_code}")
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Tenta extrair via __NEXT_DATA__ (JSON estruturado do Next.js)
        next_data_tag = soup.find("script", id="__NEXT_DATA__")
        if next_data_tag and next_data_tag.string:
            data = json.loads(next_data_tag.string)
            props = data.get("props", {}).get("pageProps", {})
            products = (
                props.get("results", {}).get("products", [])
                or props.get("products", [])
            )
            for p in products:
                title = p.get("name") or p.get("title") or ""
                price = p.get("price") or p.get("lowestPrice")
                if isinstance(price, dict):
                    price = price.get("value") or price.get("raw")
                href = p.get("url") or p.get("permalink") or ""
                if href and href.startswith("/"):
                    href = f"https://www.buscape.com.br{href}"
                if title and price:
                    items.append({
                        "title": title,
                        "price": float(price),
                        "link": href or url,
                        "source": "Buscapé"
                    })

        # 2. Fallback via HTML cards caso o schema JSON mude
        if not items:
            for card in soup.select("[data-testid='product-card'], a[href*='/']"):
                title_el = card.select_one("h2, [data-testid='product-card::name']")
                price_el = card.select_one("[data-testid='product-card::price'], p")
                if not title_el or not price_el:
                    continue
                price_txt = price_el.get_text(" ", strip=True)
                if "R$" not in price_txt:
                    continue
                price_val = parse_brl(price_txt)
                href = card.get("href") or ""
                if not href:
                    a_tag = card.find("a", href=True)
                    href = a_tag["href"] if a_tag else url
                if href.startswith("/"):
                    href = f"https://www.buscape.com.br{href}"
                if price_val:
                    items.append({
                        "title": title_el.get_text(" ", strip=True),
                        "price": price_val,
                        "link": href,
                        "source": "Buscapé"
                    })
    except Exception as e:
        print(f"[Buscapé] Erro em '{query}': {e}")
    return items


def search_ml_web(query):
    """Fallback direto na busca web do Mercado Livre Brasil"""
    slug = quote_plus(query).replace("+", "-")
    url = f"https://lista.mercadolivre.com.br/{slug}_Orden_PRICE_NoIndex_True"
    items = []
    try:
        resp = requests.get(url, impersonate="chrome124", timeout=20)
        print(f"[ML Web] '{query}' -> HTTP {resp.status_code}")
        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        for card in soup.select("li.ui-search-layout__item, div.poly-card"):
            title_el = card.select_one("h2, h3, .poly-component__title")
            link_el = card.select_one("a[href]")
            frac_el = card.select_one(".andes-money-amount__fraction")
            cents_el = card.select_one(".andes-money-amount__cents")
            if not title_el or not frac_el:
                continue
            frac = re.sub(r"\D", "", frac_el.get_text())
            cents = re.sub(r"\D", "", cents_el.get_text()) if cents_el else "00"
            if not frac:
                continue
            price_val = float(f"{frac}.{cents}")
            href = link_el["href"].split("#")[0] if link_el else url
            items.append({
                "title": title_el.get_text(" ", strip=True),
                "price": price_val,
                "link": href,
                "source": "Mercado Livre"
            })
    except Exception as e:
        print(f"[ML Web] Erro em '{query}': {e}")
    return items


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
        raw_results = search_buscape(target["query"]) + search_ml_web(target["query"])
        valid_items = []

        for item in raw_results:
            title = item["title"]
            price = item["price"]
            link = item["link"]
            source = item["source"]

            if not is_valid_item(title, price, target):
                continue

            valid_items.append((price, title, link, source))

            if price <= target["target_price"]:
                price_bucket = int(price // 10)
                item_hash = hashlib.md5(f"{title[:40]}_{source}_{price_bucket}".encode()).hexdigest()
                if item_hash not in state:
                    alert_msg = (
                        f"🔥 <b>META ATINGIDA: {target['name']}</b>\n\n"
                        f"📦 {title}\n"
                        f"💰 <b>{fmt_brl(price)}</b> ({source})\n"
                        f"🎯 Alvo: {fmt_brl(target['target_price'])}\n"
                        f"🔗 <a href='{link}'>Ver oferta agora</a>"
                    )
                    send_telegram(alert_msg)
                    state[item_hash] = {"title": title, "price": price, "source": source, "date": today_str}

        if not valid_items:
            boletim_lines.append(f"• <b>{target['name']}</b>\n  Sem anúncios válidos encontrados.\n")
            continue

        valid_items.sort(key=lambda x: x[0])
        best_price, best_title, best_link, best_source = valid_items[0]
        best_prices[target["id"]] = best_price

        day_record = minima_data["items"].get(target["id"])
        if not day_record or best_price < day_record["price"]:
            day_record = {"price": best_price, "time": time_str, "source": best_source}
            minima_data["items"][target["id"]] = day_record

        diff = best_price - target["target_price"]
        if diff <= 0:
            diff_txt = f"✅ <b>{fmt_brl(abs(diff))} abaixo do alvo!</b>"
        else:
            diff_txt = f"+ {fmt_brl(diff)} (acima do alvo)"

        boletim_lines.append(
            f"• <b>{target['name']}</b>\n"
            f"  Menor atual: <b>{fmt_brl(best_price)}</b> ({best_source}) | Alvo: {fmt_brl(target['target_price'])}\n"
            f"  Diferença: {diff_txt}\n"
            f"  📉 Menor do dia: {fmt_brl(day_record['price'])} ({day_record.get('source', best_source)} às {day_record['time']})\n"
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
