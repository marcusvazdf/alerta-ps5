from datetime import datetime, timezone, timedelta
import json
import os
import re
import smtplib
from email.mime.text import MIMEText
import urllib.parse

try:
    from curl_cffi import requests as http_client
    USANDO_CURL_CFFI = True
except ImportError:
    import requests as http_client
    USANDO_CURL_CFFI = False

TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
EMAIL_USER = os.environ.get("EMAIL_USER", "")
EMAIL_PASS = os.environ.get("EMAIL_PASS", "")
EMAIL_DESTINO = os.environ.get("EMAIL_USER", "")

FUSO_BR = timezone(timedelta(hours=-3))
AGORA_BR = datetime.now(FUSO_BR)
DATA_HOJE = AGORA_BR.strftime("%Y-%m-%d")

ARQUIVO_CONTROLE = "ultimo_boletim.txt"
ARQUIVO_METAS = "metas_alertadas.json"
ARQUIVO_MINIMA_DIA = "minima_diaria.json"

CUSTO_LEITOR_AVULSO = 450.00

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

FONTES_COMPARADORES = [
    ("Buscapé", "https://www.buscape.com.br"),
    ("Zoom", "https://www.zoom.com.br"),
    ("Bondfaro", "https://www.bondfaro.com.br"),
    ("JáCotei", "https://www.jacotei.com.br"),
]

# Links diretos fornecidos para leitura em tempo real (com checagem de estoque)
LINKS_DIRETOS_PS5_LEITOR = [
    {
        "loja": "Mercado Livre (Oficial PS)",
        "titulo": "PS5 Slim Disk + Astro Bot e GT7 (ML Oficial)",
        "url": "https://www.mercadolivre.com.br/console-playstation5-slim-disk-pacote-astro-bot-e-gran-turismo-7/p/MLB57083347?pdp_filters=official_store%3Aall",
    },
    {
        "loja": "Amazon BR",
        "titulo": "PlayStation 5 Slim com Leitor (Amazon)",
        "url": "https://www.amazon.com.br/dp/B0F8R9NDXC?psc=1",
    },
    {
        "loja": "Magalu",
        "titulo": "PS5 Slim Disk 1TB (Magalu)",
        "url": "https://www.magazineluiza.com.br/console-playstation-5-slim-disk-1tb-fisico-com-controle-dualsense-branco-sony/p/ch30jc3c3j/ga/pltt/",
    },
    {
        "loja": "Carrefour",
        "titulo": "PS5 Slim Disk + Astro Bot e GT7 (Carrefour)",
        "url": "https://www.carrefour.com.br/produto/console-playstation-5-slim-disk-pacote-astro-bot-e-gran-turismo-7-336324400",
    },
]

PRODUTOS = [
    {
        "id": "ps5_leitor",
        "nome": "PS5 Slim com Leitor 1TB",
        "query": "PlayStation 5 Slim 1TB com Leitor",
        "preco_min": 2800.00,
        "preco_alvo": 3999.99,
        "obrigatorias": ["slim"],
        "alguma_de": ["leitor", "disk", "disco", "1tb"],
        "proibidas": [
            "digital", "sem leitor", "controle", "dualsense",
            "cabo", "suporte", "capa", "usado", "reembalado"
        ],
    },
    {
        "id": "ps5_digital",
        "nome": "PS5 Slim Digital 825GB/1TB",
        "query": "PlayStation 5 Slim Digital",
        "preco_min": 2600.00,
        "preco_alvo": 3550.00,
        "obrigatorias": ["slim", "digital"],
        "alguma_de": ["825gb", "1tb", "console", "playstation", "ps5"],
        "proibidas": [
            "com leitor", "controle", "dualsense", "cabo",
            "suporte", "capa", "usado", "reembalado"
        ],
    },
    {
        "id": "ar_lg",
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

def fazer_get(url, timeout=20):
    if USANDO_CURL_CFFI:
        return http_client.get(url, headers=HEADERS, impersonate="chrome124", timeout=timeout)
    return http_client.get(url, headers=HEADERS, timeout=timeout)

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

def ler_metas_alertadas():
    if os.path.exists(ARQUIVO_METAS):
        try:
            with open(ARQUIVO_METAS, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def salvar_metas_alertadas(dados):
    with open(ARQUIVO_METAS, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def ler_minima_diaria():
    if os.path.exists(ARQUIVO_MINIMA_DIA):
        try:
            with open(ARQUIVO_MINIMA_DIA, "r", encoding="utf-8") as f:
                dados = json.load(f)
                if dados.get("data") == DATA_HOJE:
                    return dados
        except Exception:
            pass
    return {"data": DATA_HOJE, "registros": {}}

def salvar_minima_diaria(dados):
    with open(ARQUIVO_MINIMA_DIA, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

def enviar_telegram(mensagem):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }
    if USANDO_CURL_CFFI:
        http_client.post(url, json=payload, timeout=10)
    else:
        http_client.post(url, json=payload, timeout=10)

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

def extrair_ld_json_ofertas(html):
    precos_disponiveis = []
    esgotado_explicitamente = False

    for match_ld in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
        try:
            dados = json.loads(match_ld)
        except json.JSONDecodeError:
            continue

        pilha = [dados]
        while pilha:
            atual = pilha.pop()
            if isinstance(atual, dict):
                offers = atual.get("offers")
                if isinstance(offers, dict):
                    offers = [offers]
                if isinstance(offers, list):
                    for of in offers:
                        if not isinstance(of, dict):
                            continue
                        avail = str(of.get("availability", "")).lower()
                        if "outofstock" in avail or "soldout" in avail or "discontinued" in avail:
                            esgotado_explicitamente = True
                            continue
                        val = of.get("lowPrice") or of.get("price")
                        if val is not None:
                            try:
                                p = float(str(val).replace(",", "."))
                                if p > 0:
                                    precos_disponiveis.append(p)
                            except ValueError:
                                pass
                for v in atual.values():
                    if isinstance(v, (dict, list)):
                        pilha.append(v)
            elif isinstance(atual, list):
                pilha.extend(atual)

    return precos_disponiveis, esgotado_explicitamente

def consultar_links_diretos(preco_min):
    resultados = []

    for item in LINKS_DIRETOS_PS5_LEITOR:
        loja = item["loja"]
        url = item["url"]
        try:
            resp = fazer_get(url, timeout=20)
            if resp.status_code != 200:
                continue

            html = resp.text
            html_lower = html.lower()

            # 1. Tenta extrair via JSON-LD estruturado (funciona em ML, Magalu, Carrefour e parte da Amazon)
            precos_ld, esgotado_ld = extrair_ld_json_ofertas(html)
            precos_validos = [p for p in precos_ld if preco_min <= p <= 7500.0]

            # 2. Regras específicas por loja caso o JSON-LD não traga o preço à vista
            if not precos_validos:
                if "amazon.com.br" in url:
                    if "não disponível" in html_lower or "indisponível" in html_lower:
                        continue
                    # Preço principal no box da Amazon
                    m_amz = re.search(r'"priceAmount"\s*:\s*(\d+\.\d{2})', html)
                    if m_amz:
                        p = float(m_amz.group(1))
                        if preco_min <= p <= 7500.0:
                            precos_validos.append(p)

                elif "mercadolivre.com.br" in url:
                    if "publicação pausada" in html_lower or "anúncio pausado" in html_lower or "estoque esgotado" in html_lower:
                        continue
                    for m_ml in re.findall(r'"price"\s*:\s*(\d+(?:\.\d{1,2})?)', html):
                        p = float(m_ml)
                        if preco_min <= p <= 7500.0:
                            precos_validos.append(p)

                elif "magazineluiza.com.br" in url or "carrefour.com.br" in url:
                    if "produto indisponível" in html_lower or "esgotado" in html_lower and "avise-me" in html_lower:
                        continue
                    for m_gen in re.findall(r'"(?:bestPrice|pixPrice|spotPrice|price)"\s*:\s*"?(\d+(?:\.\d{1,2})?)"?', html):
                        p = float(m_gen)
                        if preco_min <= p <= 7500.0:
                            precos_validos.append(p)

            if precos_validos:
                menor_loja = min(precos_validos)
                resultados.append({
                    "titulo": item["titulo"],
                    "preco": menor_loja,
                    "link": url,
                    "fonte": f"Direto • {loja}",
                })
        except Exception as erro:
            print(f"Erro leitura direta ({loja}): {erro}")

    return resultados

def extrair_produtos_json(obj, encontrados, base_url, nome_fonte):
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
                link = f"{base_url}{link}"
            encontrados.append({
                "titulo": str(nome).strip(),
                "preco": preco,
                "link": link,
                "fonte": nome_fonte,
            })

        for v in obj.values():
            extrair_produtos_json(v, encontrados, base_url, nome_fonte)
    elif isinstance(obj, list):
        for item in obj:
            extrair_produtos_json(item, encontrados, base_url, nome_fonte)

def analisar_produto(produto):
    q_encoded = urllib.parse.quote(produto["query"])
    brutos = []
    erros = []

    for nome_fonte, base_url in FONTES_COMPARADORES:
        url = f"{base_url}/search?q={q_encoded}"
        try:
            resp = fazer_get(url, timeout=20)
            if resp.status_code != 200:
                erros.append(f"{nome_fonte}: HTTP {resp.status_code}")
                continue

            html = resp.text

            match_next = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if match_next:
                try:
                    dados = json.loads(match_next.group(1))
                    extrair_produtos_json(dados, brutos, base_url, nome_fonte)
                except json.JSONDecodeError:
                    pass

            for match_ld in re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL):
                try:
                    dados_ld = json.loads(match_ld)
                    extrair_produtos_json(dados_ld, brutos, base_url, nome_fonte)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            erros.append(f"{nome_fonte}: {e}")

    ofertas_validas = []
    vistos = set()

    for item in brutos:
        titulo_orig = item["titulo"]
        titulo = titulo_orig.lower()
        preco = item["preco"]
        link = item["link"] or f"https://www.buscape.com.br/search?q={q_encoded}"

        if preco < produto["preco_min"]:
            continue

        if not all(p in titulo for p in produto["obrigatorias"]):
            continue

        if produto["alguma_de"] and not any(p in titulo for p in produto["alguma_de"]):
            continue

        if any(p in titulo for p in produto["proibidas"]):
            continue

        chave = (titulo_orig, preco, item["fonte"])
        if chave in vistos:
            continue
        vistos.add(chave)

        ofertas_validas.append({
            "titulo": titulo_orig,
            "preco": preco,
            "link": link,
            "fonte": item["fonte"],
        })

    # Se for o PS5 Slim com Leitor, soma também a leitura direta nos 4 links oficiais
    if produto["id"] == "ps5_leitor":
        diretas = consultar_links_diretos(produto["preco_min"])
        ofertas_validas.extend(diretas)

    ofertas_validas.sort(key=lambda x: x["preco"])
    erro_geral = "; ".join(erros) if (not ofertas_validas and len(erros) == len(FONTES_COMPARADORES)) else None
    return ofertas_validas, erro_geral

def gerar_veredito_ps5(menores_atuais):
    leitor = menores_atuais.get("ps5_leitor")
    digital = menores_atuais.get("ps5_digital")

    if not leitor or not digital:
        return None

    preco_leitor = leitor["preco"]
    preco_digital = digital["preco"]
    combo_digital = preco_digital + CUSTO_LEITOR_AVULSO
    diferenca_combo = preco_leitor - combo_digital

    if diferenca_combo > 0:
        return (
            f"⚖️ *Análise Digital + Leitor ({formatar_reais(CUSTO_LEITOR_AVULSO)}):*\n"
            f"  • Combo Digital + Leitor: *{formatar_reais(combo_digital)}*\n"
            f"  • Com Leitor de Fábrica: *{formatar_reais(preco_leitor)}*\n"
            f"  ✅ *Veredito:* Vale a pena o *Digital + Leitor avulso* (economia de *{formatar_reais(diferenca_combo)}*)."
        )
    elif diferenca_combo < 0:
        return (
            f"⚖️ *Análise Digital + Leitor ({formatar_reais(CUSTO_LEITOR_AVULSO)}):*\n"
            f"  • Combo Digital + Leitor: *{formatar_reais(combo_digital)}*\n"
            f"  • Com Leitor de Fábrica: *{formatar_reais(preco_leitor)}*\n"
            f"  ✅ *Veredito:* Melhor manter o *Com Leitor 1TB de fábrica* (sai *{formatar_reais(abs(diferenca_combo))}* mais barato e já vem com 1TB)."
        )
    else:
        return (
            f"⚖️ *Análise Digital + Leitor ({formatar_reais(CUSTO_LEITOR_AVULSO)}):*\n"
            f"  • Ambos empatam em *{formatar_reais(preco_leitor)}*.\n"
            f"  ✅ *Veredito:* Melhor manter o *Com Leitor 1TB de fábrica* pelo SSD maior."
        )

if __name__ == "__main__":
    blocos_email_urgente = []
    resumo_status = []
    menores_atuais = {}

    chave_hora_atual = AGORA_BR.strftime("%Y-%m-%d-%H")
    ultimo_enviado = ler_ultimo_boletim()

    metas_alertadas = ler_metas_alertadas()
    metas_atualizadas = False

    minima_diaria = ler_minima_diaria()
    registros_dia = minima_diaria["registros"]
    minima_atualizada = False

    dentro_janela_boletim = (6 <= AGORA_BR.hour <= 23) or (AGORA_BR.hour == 0)
    enviar_status_periodico = dentro_janela_boletim and (chave_hora_atual != ultimo_enviado)

    for prod in PRODUTOS:
        ofertas, erro = analisar_produto(prod)
        alvo = prod["preco_alvo"]
        prod_id = prod["id"]

        if erro:
            resumo_status.append(f"• *{prod['nome']}:* {erro}")
            continue

        if not ofertas:
            resumo_status.append(
                f"• *{prod['nome']}:* Nenhum anúncio válido encontrado com os filtros atuais."
            )
            continue

        menor = ofertas[0]
        menores_atuais[prod_id] = menor

        reg_atual = registros_dia.get(prod_id)
        if reg_atual is None or menor["preco"] < reg_atual["preco"]:
            registros_dia[prod_id] = {
                "preco": menor["preco"],
                "fonte": menor["fonte"],
                "hora": AGORA_BR.strftime("%H:%M"),
            }
            minima_atualizada = True

        recorde_dia = registros_dia[prod_id]
        texto_recorde_dia = (
            f"📉 Menor do dia: *{formatar_reais(recorde_dia['preco'])}* "
            f"({recorde_dia['fonte']} às {recorde_dia['hora']})"
        )

        diferenca = menor["preco"] - alvo
        sinal = "+" if diferenca > 0 else "-"
        diff_formatada = f"{sinal} {formatar_reais(abs(diferenca))}"

        if diferenca <= 0:
            chave_prod = prod["nome"]
            ultimo_preco_alertado = metas_alertadas.get(chave_prod)

            if ultimo_preco_alertado is None or menor["preco"] < ultimo_preco_alertado:
                metas_alertadas[chave_prod] = menor["preco"]
                metas_atualizadas = True

                msg_tg = (
                    f"🚨 *META ATINGIDA: {prod['nome']}*\n\n"
                    f"📦 *Anúncio:* {menor['titulo']} ({menor['fonte']})\n"
                    f"💰 *Menor preço atual:* {formatar_reais(menor['preco'])}\n"
                    f"🎯 *Seu alvo:* {formatar_reais(alvo)}\n"
                    f"📉 *Diferença:* *{diff_formatada}* (abaixo do alvo!)\n"
                    f"🔗 [Ver lojas e ofertas]({menor['link']})"
                )
                enviar_telegram(msg_tg)

                blocos_email_urgente.append(
                    f"========================================\n"
                    f"META ATINGIDA: {prod['nome']}\n"
                    f"Fonte: {menor['fonte']}\n"
                    f"Anúncio: {menor['titulo']}\n"
                    f"Menor preço atual: {formatar_reais(menor['preco'])}\n"
                    f"Seu alvo: {formatar_reais(alvo)}\n"
                    f"Diferença: {diff_formatada}\n"
                    f"Link: {menor['link']}\n"
                )

            resumo_status.append(
                f"• *{prod['nome']}* ✅ *NO ALVO!*\n"
                f"  Menor atual: *{formatar_reais(menor['preco'])}* ({menor['fonte']}) | Alvo: {formatar_reais(alvo)}\n"
                f"  {texto_recorde_dia}\n"
                f"  🔗 [Ver menor preço]({menor['link']})"
            )
        else:
            if prod["nome"] in metas_alertadas:
                del metas_alertadas[prod["nome"]]
                metas_atualizadas = True

            resumo_status.append(
                f"• *{prod['nome']}*\n"
                f"  Menor atual: *{formatar_reais(menor['preco'])}* ({menor['fonte']}) | Alvo: {formatar_reais(alvo)}\n"
                f"  Diferença: *{diff_formatada}* (acima do alvo)\n"
                f"  {texto_recorde_dia}\n"
                f"  🔗 [Ver menor preço]({menor['link']})"
            )

    if metas_atualizadas:
        salvar_metas_alertadas(metas_alertadas)

    if minima_atualizada or not os.path.exists(ARQUIVO_MINIMA_DIA):
        salvar_minima_diaria(minima_diaria)

    if blocos_email_urgente:
        qtd = len(blocos_email_urgente)
        enviar_email(
            f"🚨 Meta Atingida: {qtd} {'produto' if qtd == 1 else 'produtos'} no alvo!",
            "O robô encontrou oferta(s) no seu preço alvo ou abaixo:\n\n" + "\n".join(blocos_email_urgente),
        )

    if enviar_status_periodico and resumo_status:
        veredito = gerar_veredito_ps5(menores_atuais)
        if veredito:
            resumo_status.append(veredito)

        msg_boletim = (
            f"📊 *Boletim de Preços ({AGORA_BR.strftime('%H:%M')})*\n\n"
            + "\n\n".join(resumo_status)
        )
        enviar_telegram(msg_boletim)
        salvar_ultimo_boletim(chave_hora_atual)
