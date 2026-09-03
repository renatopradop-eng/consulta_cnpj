import json
import os
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file, session

load_dotenv()

import api_client
from utils import build_xlsx, flatten_records, rotulo_coluna

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-troque-me")

# Resultados acumulados por sessão (uso local/pessoal — guardado em memória do processo).
RESULTS_BY_SESSION = {}

FORM_FIELDS = [
    "texto", "cnpj", "cnpj_raiz", "bairro", "cep", "ddd",
    "codigo_atividade_principal", "codigo_atividade_secundaria", "codigo_natureza_juridica",
    "matriz_filial", "capital_social_de", "capital_social_ate",
    "data_abertura_de", "data_abertura_ate",
]
FORM_CHECKBOXES = [
    "incluir_atividade_secundaria", "somente_mei", "excluir_mei", "com_email", "com_telefone",
]
FORM_LISTAS = ["campos_busca", "situacao_cadastral", "uf", "municipio"]

UFS = [
    ("AC", "Acre"), ("AL", "Alagoas"), ("AP", "Amapá"), ("AM", "Amazonas"),
    ("BA", "Bahia"), ("CE", "Ceará"), ("DF", "Distrito Federal"), ("ES", "Espírito Santo"),
    ("GO", "Goiás"), ("MA", "Maranhão"), ("MT", "Mato Grosso"), ("MS", "Mato Grosso do Sul"),
    ("MG", "Minas Gerais"), ("PA", "Pará"), ("PB", "Paraíba"), ("PR", "Paraná"),
    ("PE", "Pernambuco"), ("PI", "Piauí"), ("RJ", "Rio de Janeiro"), ("RN", "Rio Grande do Norte"),
    ("RS", "Rio Grande do Sul"), ("RO", "Rondônia"), ("RR", "Roraima"), ("SC", "Santa Catarina"),
    ("SP", "São Paulo"), ("SE", "Sergipe"), ("TO", "Tocantins"),
]
SIGLAS_VALIDAS = {sigla for sigla, _ in UFS}

IBGE_MUNICIPIOS_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
_municipios_cache = {}

PAGE_SIZE_OPTIONS = ["10", "20", "50", "100", "todos"]
PAGE_SIZE_PADRAO = "20"

# Teto de segurança: quantos registros no máximo o app busca automaticamente
# na API ao navegar pela paginação, para não estourar créditos numa única ação.
MAX_REGISTROS_CARREGADOS = 10000


def _session_id():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _read_filtros(form):
    filtros = {campo: form.get(campo, "") for campo in FORM_FIELDS}
    for campo in FORM_LISTAS:
        filtros[campo] = form.getlist(campo)
    for campo in FORM_CHECKBOXES:
        filtros[campo] = form.get(campo) == "on"
    return filtros


def _resolver_tamanho(valor):
    return valor if valor in PAGE_SIZE_OPTIONS else PAGE_SIZE_PADRAO


def _linhas_necessarias(tamanho, pagina_exibicao, total_estimado, total_carregado):
    if tamanho == "todos":
        alvo = total_estimado if total_estimado is not None else total_carregado
    else:
        alvo = pagina_exibicao * int(tamanho)
    return min(alvo, MAX_REGISTROS_CARREGADOS)


def _garantir_dados_carregados(sid, estado, pagina_exibicao_raw, tamanho_raw):
    """Busca páginas adicionais na API sob demanda até ter carregado o suficiente
    para satisfazer a página/tamanho de exibição pedidos (respeitando o teto de
    segurança MAX_REGISTROS_CARREGADOS)."""
    tamanho = _resolver_tamanho(tamanho_raw if tamanho_raw is not None else estado.get("tamanho", PAGE_SIZE_PADRAO))
    try:
        pagina_exibicao = int(pagina_exibicao_raw)
    except (TypeError, ValueError):
        pagina_exibicao = 1

    linhas_necessarias = _linhas_necessarias(tamanho, pagina_exibicao, estado.get("total"), len(estado["empresas"]))

    while len(estado["empresas"]) < linhas_necessarias:
        total_atual = estado.get("total")
        if total_atual is not None and len(estado["empresas"]) >= total_atual:
            break
        proxima_pagina_api = estado.get("ultima_pagina_api", 1) + 1
        try:
            novas_empresas, total, _raw = api_client.search(estado["filtros"], pagina=proxima_pagina_api)
        except api_client.CasaDosDadosError:
            break
        if not novas_empresas:
            break
        estado["empresas"] = estado["empresas"] + novas_empresas
        estado["total"] = total
        estado["ultima_pagina_api"] = proxima_pagina_api
        estado["colunas"], estado["linhas"] = flatten_records(estado["empresas"])

    estado["limite_atingido"] = (
        len(estado["empresas"]) >= MAX_REGISTROS_CARREGADOS
        and (estado.get("total") is None or len(estado["empresas"]) < estado["total"])
    )
    RESULTS_BY_SESSION[sid] = estado
    return estado


def _paginar_estado(estado, pagina_raw="1", tamanho_raw=None):
    """Recorta estado['linhas'] para exibição, sem alterar os dados completos (usados na exportação)."""
    if not estado:
        return estado

    estado = dict(estado)
    if tamanho_raw is not None:
        estado["tamanho"] = _resolver_tamanho(tamanho_raw)
    else:
        estado.setdefault("tamanho", PAGE_SIZE_PADRAO)

    linhas = estado.get("linhas", [])
    total_relatado = estado.get("total")
    if total_relatado is not None:
        total_alvo = max(min(total_relatado, MAX_REGISTROS_CARREGADOS), len(linhas))
    else:
        total_alvo = len(linhas)

    if estado["tamanho"] == "todos":
        tamanho = max(total_alvo, 1)
    else:
        tamanho = int(estado["tamanho"])

    total_paginas = max((total_alvo + tamanho - 1) // tamanho, 1)

    try:
        pagina = int(pagina_raw)
    except (TypeError, ValueError):
        pagina = 1
    pagina = min(max(pagina, 1), total_paginas)

    inicio = (pagina - 1) * tamanho
    fim = inicio + tamanho

    estado["pagina_atual"] = pagina
    estado["total_paginas"] = total_paginas
    estado["linhas_pagina"] = linhas[inicio:fim]
    return estado


def _render(filtros, estado, erro, **extra):
    if estado and estado.get("colunas"):
        estado = dict(estado)
        estado["rotulos"] = {col: rotulo_coluna(col) for col in estado["colunas"]}
    return render_template("index.html", filtros=filtros, estado=estado, erro=erro, ufs=UFS, **extra)


@app.route("/", methods=["GET"])
def index():
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    filtros = estado["filtros"] if estado else {}
    if estado:
        pagina_raw = request.args.get("pagina", "1")
        tamanho_raw = request.args.get("tamanho")
        estado = _garantir_dados_carregados(sid, estado, pagina_raw, tamanho_raw)
        estado = _paginar_estado(estado, pagina_raw, tamanho_raw)
        RESULTS_BY_SESSION[sid]["tamanho"] = estado["tamanho"]
    return _render(filtros, estado, None)


@app.route("/limpar_campos", methods=["GET"])
def limpar_campos():
    sid = _session_id()
    estado = _paginar_estado(RESULTS_BY_SESSION.get(sid))
    return _render({}, estado, None)


@app.route("/buscar", methods=["POST"])
def buscar():
    sid = _session_id()
    filtros = _read_filtros(request.form)

    estado_anterior = RESULTS_BY_SESSION.get(sid)
    tamanho_anterior = estado_anterior.get("tamanho") if estado_anterior else None

    try:
        empresas, total, _raw = api_client.search(filtros, pagina=1)
    except api_client.CasaDosDadosError as exc:
        estado = _paginar_estado(estado_anterior)
        return _render(filtros, estado, str(exc))

    colunas, linhas = flatten_records(empresas)

    estado = {
        "filtros": filtros,
        "empresas": empresas,
        "linhas": linhas,
        "total": total,
        "colunas": colunas,
        "tamanho": tamanho_anterior or PAGE_SIZE_PADRAO,
        "ultima_pagina_api": 1,
    }
    RESULTS_BY_SESSION[sid] = estado
    estado = _garantir_dados_carregados(sid, estado, "1", None)
    estado = _paginar_estado(estado, pagina_raw="1")
    RESULTS_BY_SESSION[sid] = estado

    return _render(filtros, estado, None)


@app.route("/exportar", methods=["GET"])
def exportar():
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    if not estado or not estado.get("empresas"):
        return _render({}, _paginar_estado(estado), "Nenhum resultado para exportar. Faça uma busca primeiro.")

    buffer = build_xlsx(estado["empresas"])
    return send_file(
        buffer,
        as_attachment=True,
        download_name="empresas_casadosdados.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/debug/bruto", methods=["GET"])
def debug_bruto():
    """Mostra o JSON bruto da 1ª empresa carregada e os detalhes da última
    chamada feita à API, para conferir se os parâmetros certos foram
    enviados e quais nomes de campo a API está devolvendo."""
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    if not estado or not estado.get("empresas"):
        return Response("Nenhum resultado carregado. Faça uma busca primeiro.", mimetype="text/plain")

    partes = [
        "URL da última chamada à API:",
        api_client.ULTIMA_REQUISICAO.get("url", "(indisponível)"),
        "",
        "Payload (corpo) enviado:",
        json.dumps(api_client.ULTIMA_REQUISICAO.get("payload_enviado", {}), indent=2, ensure_ascii=False, default=str),
        "",
        "JSON do primeiro resultado carregado:",
        json.dumps(estado["empresas"][0], indent=2, ensure_ascii=False, default=str),
    ]
    return Response("\n".join(partes), mimetype="text/plain; charset=utf-8")


@app.route("/limpar", methods=["POST"])
def limpar():
    sid = _session_id()
    RESULTS_BY_SESSION.pop(sid, None)
    return _render({}, None, None)


@app.route("/api/municipios", methods=["GET"])
def api_municipios():
    ufs_param = request.args.get("ufs", "")
    ufs = [u.strip().upper() for u in ufs_param.split(",") if u.strip()]
    ufs = [u for u in ufs if u in SIGLAS_VALIDAS]

    resultado = {}
    for uf in ufs:
        if uf not in _municipios_cache:
            try:
                resp = requests.get(IBGE_MUNICIPIOS_URL.format(uf=uf), timeout=10)
                resp.raise_for_status()
                nomes = sorted({item["nome"] for item in resp.json()})
                _municipios_cache[uf] = nomes
            except (requests.RequestException, ValueError, KeyError):
                _municipios_cache[uf] = []
        resultado[uf] = _municipios_cache[uf]

    return jsonify(resultado)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
