def _network_set_cookie_params(raw):
    params = {
        "name": raw["name"],
        "value": raw["value"],
        "path": raw.get("path") or "/",
    }
    if raw.get("domain"):
        params["domain"] = raw["domain"]
    if raw.get("secure"):
        params["secure"] = True
    if raw.get("httpOnly"):
        params["httpOnly"] = True
    ss = raw.get("sameSite")
    if ss:
        params["sameSite"] = ss
    exp = raw.get("expiry")
    if exp is not None:
        params["expires"] = int(exp)
    return params

def decodificar_bytes_resposta_http(raw):
    if not raw:
        return ""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    try:
        return raw.decode("cp1252")
    except UnicodeDecodeError:
        pass
    return raw.decode("latin-1")

def texto_da_celula(td):
    texto = td.get_text(separator=" ", strip=True)
    partes_botao = []
    for inp in td.find_all("input"):
        oc = (inp.get("onclick") or "").strip()
        if not oc:
            continue
        titulo = (inp.get("title") or inp.get("alt") or "").strip()
        if titulo:
            partes_botao.append(f"{titulo}: {oc}")
        else:
            partes_botao.append(oc)
    if partes_botao:
        botoes = " | ".join(partes_botao)
        if texto:
            return f"{texto} | {botoes}"
        return botoes
    return texto

def extrair_somente_imprimir_declaracao(texto_ultima_celula):
    if not texto_ultima_celula:
        return texto_ultima_celula
    prefixo = "Imprimir Declaração"
    for parte in texto_ultima_celula.split(" | "):
        s = parte.strip()
        if s.startswith(prefixo):
            resto = s[len(prefixo) :].lstrip()
            if resto.startswith(":"):
                resto = resto[1:].lstrip()
            return resto
    return ""
