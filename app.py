import os
import uuid

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request, send_file, session

load_dotenv()

import api_client
from utils import build_xlsx, flatten_records

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
    total = len(linhas)

    if estado["tamanho"] == "todos":
        tamanho = max(total, 1)
    else:
        tamanho = int(estado["tamanho"])

    total_paginas = max((total + tamanho - 1) // tamanho, 1)

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
    return render_template("index.html", filtros=filtros, estado=estado, erro=erro, ufs=UFS, **extra)


@app.route("/", methods=["GET"])
def index():
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    filtros = estado["filtros"] if estado else {}
    estado = _paginar_estado(estado, request.args.get("pagina", "1"), request.args.get("tamanho"))
    if estado:
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
    acao = request.form.get("acao", "buscar")

    estado_anterior = RESULTS_BY_SESSION.get(sid)
    pagina_api = 1
    empresas_acumuladas = []
    tamanho_anterior = estado_anterior.get("tamanho") if estado_anterior else None
    if acao == "carregar_mais" and estado_anterior:
        filtros = estado_anterior["filtros"]
        pagina_api = estado_anterior["pagina"] + 1
        empresas_acumuladas = estado_anterior["empresas"]

    try:
        empresas, total, _raw = api_client.search(filtros, pagina=pagina_api)
    except api_client.CasaDosDadosError as exc:
        estado = _paginar_estado(estado_anterior)
        return _render(filtros, estado, str(exc))

    todas_empresas = empresas_acumuladas + empresas
    colunas, linhas = flatten_records(todas_empresas)

    estado = {
        "filtros": filtros,
        "pagina": pagina_api,
        "empresas": todas_empresas,
        "linhas": linhas,
        "total": total,
        "colunas": colunas,
        "ultima_pagina_vazia": len(empresas) == 0,
        "tamanho": tamanho_anterior or PAGE_SIZE_PADRAO,
    }
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
