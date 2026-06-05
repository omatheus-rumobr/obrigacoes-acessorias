import base64
from datetime import datetime
import json
from pathlib import Path
import re
from time import sleep
from urllib.parse import urlencode, urljoin, urlparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
import undetected_chromedriver as uc

from funcoes import (
    _network_set_cookie_params,
    decodificar_bytes_resposta_http,
    extrair_somente_imprimir_declaracao,
    texto_da_celula,
)

COOKIES_PATH = Path("temp") / "cookies.json"
SAIDA_JSON_PATH = Path("temp") / "consulta_dctf.json"
PDFS_DIR = Path("pdfs")
DECS_DIR = Path("decs")
PERDCOMPS_DIR = Path("perdcomps")
url = "https://cav.receita.fazenda.gov.br/ecac/"

primeira_requisicao_url = "https://cav.receita.fazenda.gov.br/Servicos/ATSPO/DCTF/Consulta/consulta.asp"
inicio_impr_url = ("https://cav.receita.fazenda.gov.br/Servicos/ATSPO/DCTF/Consulta/Inicio_Impr.asp")
warmup_referer = ("https://cav.receita.fazenda.gov.br/ecac/Aplicacao.aspx?id=14&origem=menu")
DECWEB_URL = "https://cav.receita.fazenda.gov.br/Servicos/ATSDR/DECWEB/decweb.asp"
DECWEB_GERA_DEC_URL = ("https://cav.receita.fazenda.gov.br/Servicos/ATSDR/DECWEB/geraArquivoDEC.asp")
DECWEB_HTML_DIR = Path("temp") / "decweb"
PERDCOMP_URL_BASE = "https://www3.cav.receita.fazenda.gov.br/perdcomp-web/rest/api/documento-enviado"
PERDCOMP_JSON_PATH = Path("temp") / "perdcomp_documento_enviado.json"
PERDCOMP_REFERER = "https://www3.cav.receita.fazenda.gov.br/perdcomp-web/"
PERDCOMP_REFERER_PDF = "https://cav.receita.fazenda.gov.br/ecac/Aplicacao.aspx?id=10006&origem=menu"
PERDCOMP_NUMEROS_JSON_PATH = Path("temp") / "perdcomp_numeros_ui.json"
PERDCOMP_MAX_PAGES = 116
PERIODOS = "01/2021,02/2021,03/2021,04/2021,05/2021,06/2021,07/2021,08/2021,09/2021,10/2021,11/2021,12/2021,01/2022,02/2022,03/2022,04/2022,05/2022,06/2022,07/2022,08/2022,09/2022,10/2022,11/2022,12/2022,01/2023,02/2023,03/2023,04/2023,05/2023,06/2023,07/2023,08/2023,09/2023,10/2023,11/2023,12/2023,01/2024,02/2024,03/2024,04/2024,05/2024,06/2024,07/2024,08/2024,09/2024,10/2024,11/2024,12/2024,01/2025,02/2025,03/2025,04/2025,05/2025,06/2025,07/2025,08/2025,09/2025,10/2025,11/2025,12/2025,01/2026,02/2026,03/2026,04/2026,05/2026"
CHROME_VERSION = 147

_FETCH_IMPR_JS = """
var cb = arguments[arguments.length - 1];
var consultaUrl = arguments[0];
var imprBase = arguments[1];
var ultimoSel = arguments[2];
var ndBody = arguments[3];
var warmupRef = arguments[4];
var skipWarmup = arguments[5];

function fail(msg) {
  cb(JSON.stringify({ ok: false, err: String(msg) }));
}

function okB64(ab) {
  var bytes = new Uint8Array(ab);
  var bin = '';
  for (var i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  cb(JSON.stringify({ ok: true, b64: btoa(bin) }));
}

function doImpr() {
  var u = imprBase + '?UltimoSel=' + encodeURIComponent(ultimoSel);
  fetch(u, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Referer': consultaUrl
    },
    body: ndBody,
    credentials: 'include'
  })
    .then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          throw new Error('Inicio_Impr.asp HTTP ' + r.status + ' ' + t.slice(0, 500));
        });
      }
      return r.arrayBuffer();
    })
    .then(function (ab) { okB64(ab); })
    .catch(function (e) { fail(e); });
}

if (skipWarmup) {
  doImpr();
} else {
  fetch(consultaUrl, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
      'Referer': warmupRef,
      'Origin': 'https://cav.receita.fazenda.gov.br'
    },
    body: 'ano=0',
    credentials: 'include'
  })
    .then(function (r) {
      if (!r.ok) {
        return r.text().then(function (t) {
          throw new Error('consulta.asp HTTP ' + r.status + ' ' + t.slice(0, 500));
        });
      }
      doImpr();
    })
    .catch(function (e) { fail(e); });
}
"""


def _html_de_resposta_fetch_base64(resultado):
    if not isinstance(resultado, str):
        return "__FETCH_ERROR__resposta_invalida"
    if resultado.startswith("__FETCH_ERROR__"):
        return resultado
    try:
        raw = base64.b64decode(resultado)
    except Exception:
        return "__FETCH_ERROR__base64"
    return decodificar_bytes_resposta_http(raw)


def post_html_com_sessao(driver, post_url, body, referer):
    resultado = driver.execute_async_script(
        """
        const postUrl = arguments[0];
        const body = arguments[1];
        const referer = arguments[2];
        const done = arguments[arguments.length - 1];
        function abToB64(buffer) {
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }
        fetch(postUrl, {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
                'Referer': referer,
            },
            body: body,
        })
            .then((r) => r.arrayBuffer())
            .then((buf) => done(abToB64(buf)))
            .catch((e) => done('__FETCH_ERROR__' + String(e)));
        """,
        post_url,
        body,
        referer,
    )
    return _html_de_resposta_fetch_base64(resultado)


def get_html_via_fetch(driver, get_url, referer):
    resultado = driver.execute_async_script(
        """
        const getUrl = arguments[0];
        const referer = arguments[1];
        const done = arguments[arguments.length - 1];
        function abToB64(buffer) {
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }
        fetch(getUrl, {
            method: 'GET',
            credentials: 'include',
            headers: { Referer: referer },
        })
            .then((r) => r.arrayBuffer())
            .then((buf) => done(abToB64(buf)))
            .catch((e) => done('__FETCH_ERROR__' + String(e)));
        """,
        get_url,
        referer,
    )
    return _html_de_resposta_fetch_base64(resultado)


def _execute_async_json(driver, script, *args):
    raw = driver.execute_async_script(script, *args)
    if not isinstance(raw, str):
        raise RuntimeError(f"Resposta inesperada do navegador: {type(raw)!r}")
    return json.loads(raw)


def _montar_corpo_nd(nd_token, nd_hash_count):
    if nd_hash_count <= 0:
        return [("ND", nd_token)]
    body = [("ND", "#")] * nd_hash_count
    body.append(("ND", nd_token))
    return body


def _parse_seleciona_imprimir(texto):
    if not texto:
        return None
    m = re.search(
        r"selecionaServico\s*\(\s*['\"](ND\d+)['\"]\s*,\s*['\"](1[^'\"]*)['\"]",
        texto,
        re.I,
    )
    if not m:
        return None
    return m.group(1), m.group(2)


STATUS_RETIFICADORA_ATIVA = "Retificadora/ Ativa"
MESES_NOME_PARA_NUM = {
    "Janeiro": 1,
    "Fevereiro": 2,
    "Março": 3,
    "Marco": 3,
    "Abril": 4,
    "Maio": 5,
    "Junho": 6,
    "Julho": 7,
    "Agosto": 8,
    "Setembro": 9,
    "Outubro": 10,
    "Novembro": 11,
    "Dezembro": 12,
}


def _parse_periodos_mm_aaaa(periodos):
    """
    Converte "01/2024,02/2024" em {(2024, 1), (2024, 2)}.
    Espaços são ignorados. Entradas inválidas são descartadas.
    """
    out: set[tuple[int, int]] = set()
    for part in (periodos or "").split(","):
        s = part.strip()
        if not s:
            continue
        m = re.match(r"^(\d{2})/(\d{4})$", s)
        if not m:
            continue
        mm = int(m.group(1))
        yy = int(m.group(2))
        if 1 <= mm <= 12:
            out.add((yy, mm))
    return out


def _indices_baixar_ultimo_por_periodo_retificadora_ativa(registros):
    """
    Agrupa por período (celulas[1]).

    - Um único registro para o período: entra sempre na fila (não exige coluna 6).
    - Vários registros: só o último na ordem da lista; baixa só se celulas[6] ==
      STATUS_RETIFICADORA_ATIVA (após strip); senão vai para omitidos.

    Retorna (índices 0-based a baixar ordenados, omitidos, quantidade de períodos distintos).
    """
    indices_por_periodo: dict[str, list[int]] = {}
    for i, reg in enumerate(registros):
        cels = reg.get("celulas") or []
        if len(cels) < 2:
            continue
        periodo = cels[1]
        indices_por_periodo.setdefault(periodo, []).append(i)

    baixar: list[int] = []
    omitidos: list[tuple[str, str, int]] = []
    for periodo, idxs in indices_por_periodo.items():
        if len(idxs) == 1:
            baixar.append(idxs[0])
            continue
        i = idxs[-1]
        cels = registros[i].get("celulas") or []
        status = (cels[6] if len(cels) > 6 else "").strip()
        if status == STATUS_RETIFICADORA_ATIVA:
            baixar.append(i)
        else:
            omitidos.append((periodo, status or "(vazio)", i))

    baixar.sort()
    return baixar, omitidos, len(indices_por_periodo)


def _sanitizar_nome_arquivo(s, max_len=80):
    s = (s or "").strip()
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", s)
    s = re.sub(r"\s+", "_", s).strip("._")
    if len(s) > max_len:
        s = s[:max_len].rstrip("._")
    return s or "sem_periodo"


def _salvar_resposta_impressao(data, path_base):
    path_base.parent.mkdir(parents=True, exist_ok=True)
    ext = ".pdf" if data[:4] == b"%PDF" else ".html"
    out = path_base.with_suffix(ext)
    out.write_bytes(data)
    return out


def _parse_mes_ano_periodo(periodo):
    """
    Aceita formatos como "Março/2010" e retorna ("Março", "2010").
    Para outros formatos (Semestre/Trimestre etc.) retorna None.
    """
    s = (periodo or "").strip()
    m = re.match(r"^([^/]+)\s*/\s*(\d{4})\s*$", s)
    if not m:
        return None
    return m.group(1).strip(), m.group(2)


def _periodo_registro_esta_na_lista(periodo, permitidos):
    """
    Retorna True se o período do registro (ex.: "Março/2010") estiver em permitidos {(ano, mes)}.
    Se permitidos estiver vazio, não filtra (True).
    """
    if not permitidos:
        return True
    parsed = _parse_mes_ano_periodo(periodo)
    if not parsed:
        return False
    mes_nome, ano_str = parsed
    try:
        ano = int(ano_str)
    except ValueError:
        return False
    mes = MESES_NOME_PARA_NUM.get(mes_nome)
    if not mes:
        return False
    return (ano, mes) in permitidos


def _post_decweb_e_parse(driver, *, ano, periodo_codigo, referer):
    """
    Faz POST em decweb.asp e retorna (html_str, soup).
    """
    body = urlencode(
        {
            "Declaracao": "DCTF",
            "cboExercicio": str(ano),
            "periodo": str(periodo_codigo),
            "txtNIRF": "",
        }
    )
    html = post_html_com_sessao(driver, DECWEB_URL, body, referer)
    if isinstance(html, str) and html.startswith("__FETCH_ERROR__"):
        raise RuntimeError(html)
    soup = BeautifulSoup(html, "html.parser")
    return html, soup


def _get_bytes_via_fetch(driver, get_url, referer):
    """
    GET via fetch() no contexto do navegador, retornando bytes.
    Usar para downloads binários (ex.: .dec).
    """
    resultado = driver.execute_async_script(
        """
        const getUrl = arguments[0];
        const referer = arguments[1];
        const done = arguments[arguments.length - 1];
        function abToB64(buffer) {
            const bytes = new Uint8Array(buffer);
            let binary = '';
            for (let i = 0; i < bytes.length; i++) {
                binary += String.fromCharCode(bytes[i]);
            }
            return btoa(binary);
        }
        fetch(getUrl, {
            method: 'GET',
            credentials: 'include',
            headers: { Referer: referer },
        })
            .then((r) => r.arrayBuffer())
            .then((buf) => done(abToB64(buf)))
            .catch((e) => done('__FETCH_ERROR__' + String(e)));
        """,
        get_url,
        referer,
    )
    if not isinstance(resultado, str):
        raise RuntimeError(f"Resposta inesperada do navegador (bytes): {type(resultado)!r}")
    if resultado.startswith("__FETCH_ERROR__"):
        raise RuntimeError(resultado)
    try:
        return base64.b64decode(resultado)
    except Exception as e:
        raise RuntimeError(f"Falha ao decodificar base64 do download: {e}") from e


def _perdcomp_clicar_visualizar_documentos(driver, timeout = 25.0):
    """
    No PER/DCOMP (Angular), clica em 'Visualizar Documentos' no menu lateral.
    Usa o ícone estável `icon-VisualizarDocumento` (evita depender de _ngcontent-*).
    """
    wait = WebDriverWait(driver, timeout)
    link = wait.until(
        EC.element_to_be_clickable(
            (By.XPATH, "//a[.//i[contains(@class,'icon-VisualizarDocumento')]]")
        )
    )
    try:
        link.click()
    except Exception:
        driver.execute_script("arguments[0].click();", link)
    sleep(2)
    print("PERDCOMP: clique em 'Visualizar Documentos' concluído.")


def _get_json_via_fetch(driver, get_url, referer, *, debug = False):
    """
    GET via fetch() no contexto do navegador, retorna JSON (dict/list).
    """
    raw = driver.execute_async_script(
        """
        const getUrl = arguments[0];
        const referer = arguments[1];
        const done = arguments[arguments.length - 1];
        fetch(getUrl, {
            method: 'GET',
            credentials: 'include',
            headers: { 'Accept': 'application/json', 'Referer': referer },
        })
            .then(async (r) => {
                const ct = r.headers.get('content-type') || '';
                const urlFinal = r.url || getUrl;
                const redirected = !!r.redirected;
                const text = await r.text();
                if (!r.ok) {
                    done(JSON.stringify({ ok: false, status: r.status, url: urlFinal, redirected, ct, text: text.slice(0, 1500) }));
                    return;
                }
                try {
                    const j = JSON.parse(text);
                    done(JSON.stringify({ ok: true, status: r.status, url: urlFinal, redirected, ct, json: j }));
                } catch (e) {
                    done(JSON.stringify({ ok: false, status: r.status, url: urlFinal, redirected, ct, text: text.slice(0, 1500), err: String(e) }));
                }
            })
            .catch((e) => done(JSON.stringify({ ok: false, err: String(e), url: getUrl })));
        """,
        get_url,
        referer,
    )
    if not isinstance(raw, str):
        raise RuntimeError(f"Resposta inesperada do navegador (json): {type(raw)!r}")
    payload = json.loads(raw)
    if debug:
        print(
            {
                "ok": payload.get("ok"),
                "status": payload.get("status"),
                "url": payload.get("url"),
                "redirected": payload.get("redirected"),
                "ct": payload.get("ct"),
                "err": payload.get("err"),
                "text_prefix": (payload.get("text") or "")[:250],
            }
        )
    if not payload.get("ok"):
        msg = payload.get("err") or (
            f"HTTP {payload.get('status')} ct={payload.get('ct')!r} "
            f"redirected={payload.get('redirected')!r} url={payload.get('url')!r} "
            f"body_prefix={((payload.get('text') or '')[:250])!r}"
        )
        raise RuntimeError(msg)
    return payload.get("json")


def _html_file_to_pdf_via_cdp(driver, html_path):
    uri = html_path.resolve().as_uri()
    driver.get(uri)
    sleep(2.0)
    result = driver.execute_cdp_cmd(
        "Page.printToPDF",
        {
            "printBackground": True,
            "preferCSSPageSize": False,
            "paperWidth": 8.27,
            "paperHeight": 11.69,
            "marginTop": 0.4,
            "marginBottom": 0.4,
            "marginLeft": 0.4,
            "marginRight": 0.4,
        },
    )
    b64 = result.get("data")
    if not b64:
        raise RuntimeError(f"printToPDF sem campo data: {result!r}")
    return base64.b64decode(b64)


def _converter_htmls_em_pdfs(driver, pdfs_dir, pagina_sessao):
    htmls = sorted(pdfs_dir.glob("*.html"))
    if not htmls:
        return 0, 0
    print(f"Convertendo {len(htmls)} arquivo(s) HTML para PDF (Chrome printToPDF)…")
    driver.get(pagina_sessao)
    sleep(1.5)
    ok = 0
    falhas = 0
    for hp in htmls:
        try:
            pdf_bytes = _html_file_to_pdf_via_cdp(driver, hp)
            if len(pdf_bytes) < 8 or pdf_bytes[:4] != b"%PDF":
                raise RuntimeError("resposta não é um PDF válido")
            dest = hp.with_suffix(".pdf")
            dest.write_bytes(pdf_bytes)
            hp.unlink()
            ok += 1
        except Exception as e:
            falhas += 1
            print(f"  Aviso: não convertido {hp.name}: {e}")
            try:
                driver.get(pagina_sessao)
                sleep(0.4)
            except Exception:
                pass
    print(f"HTML→PDF: {ok} convertido(s) e .html removido(s); {falhas} falha(s) (HTML mantido).")
    try:
        driver.get(pagina_sessao)
        sleep(0.5)
    except Exception:
        pass
    return ok, falhas


def main():
    if not url or not str(url).strip():
        raise SystemExit("Defina a variável url no início do arquivo.")

    if not primeira_requisicao_url or not str(primeira_requisicao_url).strip():
        raise SystemExit("Defina a variável primeira_requisicao_url no início do arquivo.")

    data = json.loads(COOKIES_PATH.read_text(encoding="utf-8"))

    if not isinstance(data, list):
        raise SystemExit(f"Esperado lista de cookies em {COOKIES_PATH}")

    parsed = urlparse(url)

    if not parsed.scheme or not parsed.netloc:
        raise SystemExit("Defina uma url válida (com esquema e host).")

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=CHROME_VERSION)

    try:
        driver.execute_cdp_cmd("Network.enable", {})
        for raw in data:
            try:
                driver.execute_cdp_cmd(
                    "Network.setCookie",
                    _network_set_cookie_params(raw),
                )
            except Exception as e:
                print(f"Aviso: não foi possível aplicar o cookie {raw.get('name')!r}: {e}")

        driver.get(url)
        sleep(5)
        pagina_sessao = url

        html = post_html_com_sessao(
            driver,
            primeira_requisicao_url,
            "ano=0",
            url,
        )
        if isinstance(html, str) and html.startswith("__FETCH_ERROR__"):
            raise RuntimeError(html)

        soup_outer = BeautifulSoup(html, "html.parser")
        base_origin = f"{parsed.scheme}://{parsed.netloc}"
        iframe = soup_outer.find("iframe", id="frmApp")

        if iframe is None:
            iframe = soup_outer.select_one("#divApp iframe")

        if iframe is None:
            iframe = soup_outer.find("iframe")

        if iframe and iframe.get("src"):
            src = iframe["src"].strip()
            if src:
                inner_url = urljoin(base_origin + "/", src)
                driver.get(inner_url)
                sleep(5)
                pagina_sessao = inner_url
                inner_html = get_html_via_fetch(driver, inner_url, url)
                if inner_html.startswith("__FETCH_ERROR__"):
                    inner_html = driver.page_source
                soup = BeautifulSoup(inner_html, "html.parser")
            else:
                soup = soup_outer
        else:
            soup = soup_outer

        tbody = soup.find("tbody")

        if tbody:
            linhas = tbody.find_all("tr")
        else:
            tabela = soup.find("table")
            linhas = tabela.find_all("tr") if tabela else []

        registros = []
        if not linhas:
            print("Nenhuma linha (tbody/tabela) encontrada no HTML do iframe/página.")
        else:
            SAIDA_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
            for tr in linhas[1:]:
                celulas = tr.find_all(["td", "th"], recursive=False)
                if not celulas:
                    continue
                valores = [texto_da_celula(c) for c in celulas]
                if valores:
                    valores[-1] = extrair_somente_imprimir_declaracao(valores[-1])
                registros.append({"celulas": valores})
            SAIDA_JSON_PATH.write_text(
                json.dumps(registros, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Gravados {len(registros)} registros em {SAIDA_JSON_PATH}")

        if registros:
            ref_warmup = (warmup_referer or url).strip()
            nd_hash = len(registros)
            indices_baixar, omitidos_por_periodo, n_periodos = (
                _indices_baixar_ultimo_por_periodo_retificadora_ativa(registros)
            )

            permitidos = _parse_periodos_mm_aaaa(PERIODOS)
            if permitidos:
                antes = len(indices_baixar)
                indices_baixar = [
                    i
                    for i in indices_baixar
                    if _periodo_registro_esta_na_lista(
                        (registros[i].get("celulas") or ["", ""])[1] if len(registros[i].get("celulas") or []) > 1 else "",
                        permitidos,
                    )
                ]
                print(
                    f"Filtro PERIODOS={PERIODOS!r}: {len(indices_baixar)}/{antes} registro(s) na fila após filtro."
                )
            print(
                f"Baixando impressões (Inicio_Impr.asp): {len(indices_baixar)} arquivo(s) "
                f"(1 linha por período; se o período tem várias linhas, só a última e só se "
                f"celulas[6] == '{STATUS_RETIFICADORA_ATIVA}'). "
                f"Tabela: {len(registros)} linha(s); períodos distintos: {n_periodos}; "
                f"ND repetido #{nd_hash} no corpo."
            )
            if omitidos_por_periodo:
                print(
                    f"  Omitidos {len(omitidos_por_periodo)} período(s) com >1 linha "
                    f"cuja última não tem '{STATUS_RETIFICADORA_ATIVA}' em celulas[6]."
                )
                amostra = sorted(omitidos_por_periodo, key=lambda t: t[2])[:12]
                for periodo, status_lido, idx_linha in amostra:
                    print(
                        f"    ex.: período {periodo!r}, linha {idx_linha + 1}, "
                        f"celulas[6]={status_lido!r}"
                    )
                if len(omitidos_por_periodo) > len(amostra):
                    print(f"    … (+{len(omitidos_por_periodo) - len(amostra)} períodos)")

            ok = 0
            falhas = 0
            total_fila = len(indices_baixar)
            periodos_baixados: list[str] = []
            for seq, i in enumerate(indices_baixar, start=1):
                reg = registros[i]
                cels = reg.get("celulas") or []
                ultima = cels[-1] if cels else ""
                parsed = _parse_seleciona_imprimir(ultima)
                if not parsed:
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"ignorado: sem selecionaServico/ token em {ultima!r}"
                    )
                    continue
                nd_id, nd_tok = parsed
                if len(nd_tok) < 5:
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"token ND curto demais ({nd_id})"
                    )
                    continue
                ultimo_sel = nd_tok[1:5]
                nd_body = urlencode(_montar_corpo_nd(nd_tok, nd_hash))
                try:
                    payload = _execute_async_json(
                        driver,
                        _FETCH_IMPR_JS,
                        primeira_requisicao_url,
                        inicio_impr_url,
                        ultimo_sel,
                        nd_body,
                        ref_warmup,
                        True,
                    )
                except Exception as e:
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"erro script ({nd_id}): {e}"
                    )
                    continue
                if not payload.get("ok"):
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"falha ({nd_id}): {payload.get('err', payload)}"
                    )
                    continue
                try:
                    raw_pdf = base64.b64decode(payload["b64"])
                except Exception as e:
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"base64 inválido ({nd_id}): {e}"
                    )
                    continue
                periodo = cels[1] if len(cels) > 1 else ""
                slug = _sanitizar_nome_arquivo(periodo)
                path_base = PDFS_DIR / f"{seq:04d}_{slug}_{nd_id}"
                try:
                    out_path = _salvar_resposta_impressao(raw_pdf, path_base)
                except Exception as e:
                    falhas += 1
                    print(
                        f"  [fila {seq}/{total_fila}, tabela linha {i + 1}] "
                        f"erro ao gravar ({nd_id}): {e}"
                    )
                    continue
                ok += 1
                if periodo:
                    periodos_baixados.append(periodo)
                if seq == 1 or seq % 25 == 0 or seq == total_fila:
                    print(f"  … fila {seq}/{total_fila} (tabela linha {i + 1}) → {out_path.name}")
                sleep(0.35)
            print(f"Downloads concluídos: {ok} arquivo(s) em {PDFS_DIR.resolve()}; falhas: {falhas}")

        if PDFS_DIR.exists():
            _converter_htmls_em_pdfs(driver, PDFS_DIR, pagina_sessao)

        sleep(10)

        periodos_e_seus_codigos = {
            "Janeiro": "3001",
            "Fevereiro": "3002",
            "Março": "3003",
            "Abril": "3004",
            "Maio": "3005",
            "Junho": "3006",
            "Julho": "3007",
            "Agosto": "3008",
            "Setembro": "3009",
            "Outubro": "3010",
            "Novembro": "3011",
            "Dezembro": "3012",
            "1º Trimestre": "3213",
            "2º Trimestre": "3214",
        }

        # DECWEB: para cada período baixado que for do tipo Mês/Ano, consulta decweb.asp
        if registros and "periodos_baixados" in locals() and periodos_baixados:
            unicos = []
            vistos = set()
            for p in periodos_baixados:
                if p in vistos:
                    continue
                vistos.add(p)
                unicos.append(p)

            print(f"DECWEB: consultando {len(unicos)} período(s) baixado(s) (somente Mês/Ano)…")
            decweb_ok = 0
            decweb_falhas = 0
            for p in unicos:
                parsed_ma = _parse_mes_ano_periodo(p)
                if not parsed_ma:
                    continue
                mes_nome, ano = parsed_ma
                codigo = periodos_e_seus_codigos.get(mes_nome)
                if not codigo:
                    continue
                try:
                    html_decweb, soup = _post_decweb_e_parse(
                        driver, 
                        ano=ano, 
                        periodo_codigo=codigo, 
                        referer=pagina_sessao
                    )
                    if "geraArquivoDEC.asp" not in (html_decweb or ""):
                        print(f"  Aviso: DECWEB {p!r} sem referência a geraArquivoDEC.asp no HTML retornado.")
                    dec_bytes = _get_bytes_via_fetch(driver, DECWEB_GERA_DEC_URL, pagina_sessao)
                    if not dec_bytes:
                        raise RuntimeError("download .dec vazio")
                    DECS_DIR.mkdir(parents=True, exist_ok=True)
                    out_dec = DECS_DIR / f"DCTF_{ano}_{codigo}_{_sanitizar_nome_arquivo(mes_nome)}.dec"
                    out_dec.write_bytes(dec_bytes)
                    print(f"  DECWEB {p!r} → {out_dec.name} ({len(dec_bytes)} bytes)")
                    decweb_ok += 1
                except Exception as e:
                    decweb_falhas += 1
                    print(f"  Aviso: DECWEB falhou para {p!r}: {e}")
            print(f"DECWEB: concluído ({decweb_ok} OK; {decweb_falhas} falha(s)).")
        
        sleep(10)

        # PERDCOMP: paginação até falhar 3 páginas seguidas
        print("PERDCOMP: consultando documento-enviado (tpag=5)…")
        print(f"PERDCOMP: navegando para origem {PERDCOMP_REFERER!r} (evitar CORS)…")
        try:
            driver.get(PERDCOMP_REFERER)
            sleep(5)
            _perdcomp_clicar_visualizar_documentos(driver)
        except Exception as e:
            print(f"PERDCOMP: aviso ao abrir origem / menu: {e}")

        acumulado = []
        pagina = 1
        falhas_seguidas = 0
        while True:
            if PERDCOMP_MAX_PAGES and pagina > int(PERDCOMP_MAX_PAGES):
                print(f"  PERDCOMP: limite atingido (PERDCOMP_MAX_PAGES={PERDCOMP_MAX_PAGES}).")
                break
            qs = urlencode({"tpag": 5, "pag": pagina})
            req_url = f"{PERDCOMP_URL_BASE}?{qs}"
            print(req_url)
            try:
                j = _get_json_via_fetch(driver, req_url, PERDCOMP_REFERER, debug=True)
                acumulado.append({"pag": pagina, "response": j})
                falhas_seguidas = 0
                if pagina == 1 or pagina % 10 == 0:
                    print(f"  PERDCOMP: página {pagina} OK")
            except Exception as e:
                falhas_seguidas += 1
                print(f"  PERDCOMP: página {pagina} falhou ({falhas_seguidas}/3): {e}")
                if falhas_seguidas >= 3:
                    print("  PERDCOMP: encerrando (3 falhas consecutivas).")
                    break
            pagina += 1
            sleep(0.35)

        PERDCOMP_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        PERDCOMP_JSON_PATH.write_text(
            json.dumps(
                acumulado, 
                ensure_ascii=False, 
                indent=2
            ),
            encoding="utf-8",
        )
        print(f"PERDCOMP: salvo {len(acumulado)} página(s) em {PERDCOMP_JSON_PATH.resolve()}")


        # TESTE PERDCOMP: ler JSON paginado e imprimir numeroPerdcomp
        numeros_perdcomp_api = []
        try:
            permitidos = _parse_periodos_mm_aaaa(PERIODOS)
            raw_perd = json.loads(PERDCOMP_JSON_PATH.read_text(encoding="utf-8"))
            if not isinstance(raw_perd, list):
                raise RuntimeError("perdcomp_documento_enviado.json não é uma lista de páginas")
            numeros_api = []
            for page in raw_perd:
                if not isinstance(page, dict):
                    continue
                resp = page.get("response")
                if not isinstance(resp, dict):
                    continue
                resultado = resp.get("resultado")
                if not isinstance(resultado, list):
                    continue
                for item in resultado:
                    if not isinstance(item, dict):
                        continue
                    dt = item.get("dataTransmissao")
                    if not (isinstance(dt, str) and dt.strip()):
                        continue
                    try:
                        dt_norm = dt.strip().replace("Z", "+00:00")
                        dt_parsed = datetime.fromisoformat(dt_norm)
                        chave = (dt_parsed.year, dt_parsed.month)
                    except Exception:
                        continue
                    if chave not in permitidos:
                        continue
                    n = item.get("numeroPerdcomp")
                    if isinstance(n, str) and n.strip():
                        numeros_api.append(n.strip())
            vistos = set()
            numeros_api_unicos = []
            for n in numeros_api:
                if n in vistos:
                    continue
                vistos.add(n)
                numeros_api_unicos.append(n)
            print(f"PERDCOMP JSON: numeroPerdcomp extraídos: {len(numeros_api_unicos)}")
            for n in numeros_api_unicos:
                print(n)
            numeros_perdcomp_api = numeros_api_unicos
        except Exception as e:
            print(f"PERDCOMP JSON: aviso ao extrair/printar numeroPerdcomp: {e}")
        

        # PERDCOMP PDF: baixar diretamente via API copia/{numeroPerdcomp} (sem UI)
        url_perdcomp_baixar_pdf = (
            "https://www3.cav.receita.fazenda.gov.br/perdcomp-web/rest/api/documento-enviado/copia/"
        )
        if numeros_perdcomp_api:
            try:
                PERDCOMPS_DIR.mkdir(parents=True, exist_ok=True)
                print(f"PERDCOMP PDF API: baixando {len(numeros_perdcomp_api)} PDF(s) a partir do JSON…")
                ok_pdf = 0
                falhas_pdf = 0
                for idx, num_norm in enumerate(numeros_perdcomp_api, start=1):
                    pdf_url = url_perdcomp_baixar_pdf + num_norm
                    out_pdf = PERDCOMPS_DIR / f"perdcomp_{idx:04d}_{num_norm}.pdf"
                    try:
                        pdf_bytes = _get_bytes_via_fetch(driver, pdf_url, PERDCOMP_REFERER)
                        if len(pdf_bytes) < 8 or pdf_bytes[:4] != b"%PDF":
                            raise RuntimeError("resposta não parece PDF")
                        out_pdf.write_bytes(pdf_bytes)
                        ok_pdf += 1
                        if idx == 1 or idx % 25 == 0 or idx == len(numeros_perdcomp_api):
                            print(f"  … {idx}/{len(numeros_perdcomp_api)} → {out_pdf.name}")
                    except Exception as e:
                        falhas_pdf += 1
                        print(f"  [{idx}/{len(numeros_perdcomp_api)}] falha {num_norm!r}: {e}")
                    sleep(0.35)
                print(
                    f"PERDCOMP PDF API: concluído ({ok_pdf} OK; {falhas_pdf} falha(s)). "
                    f"Saída: {PERDCOMPS_DIR.resolve()}"
                )
            except Exception as e:
                print(f"PERDCOMP PDF API: aviso ao baixar PDFs via API: {e}")
        else:
            print("PERDCOMP PDF API: nenhum numeroPerdcomp disponível (lista vazia).")

        input('Digite Enter para encerrar...')
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
