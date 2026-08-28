import os
import uuid

from dotenv import load_dotenv
from flask import Flask, render_template, request, send_file, session

load_dotenv()

import api_client
from utils import build_xlsx, flatten_records

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-troque-me")

# Resultados acumulados por sessão (uso local/pessoal — guardado em memória do processo).
RESULTS_BY_SESSION = {}

FORM_FIELDS = [
    "texto", "cnpj", "cnpj_raiz", "uf", "municipio", "bairro", "cep", "ddd",
    "codigo_atividade_principal", "codigo_atividade_secundaria", "codigo_natureza_juridica",
    "matriz_filial", "capital_social_de", "capital_social_ate",
    "data_abertura_de", "data_abertura_ate",
]
FORM_CHECKBOXES = [
    "incluir_atividade_secundaria", "somente_mei", "excluir_mei", "com_email", "com_telefone",
]


def _session_id():
    if "sid" not in session:
        session["sid"] = uuid.uuid4().hex
    return session["sid"]


def _read_filtros(form):
    filtros = {campo: form.get(campo, "") for campo in FORM_FIELDS}
    filtros["campos_busca"] = form.getlist("campos_busca")
    filtros["situacao_cadastral"] = form.getlist("situacao_cadastral")
    for campo in FORM_CHECKBOXES:
        filtros[campo] = form.get(campo) == "on"
    return filtros


@app.route("/", methods=["GET"])
def index():
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    return render_template("index.html", filtros={}, estado=estado, erro=None)


@app.route("/buscar", methods=["POST"])
def buscar():
    sid = _session_id()
    filtros = _read_filtros(request.form)
    acao = request.form.get("acao", "buscar")

    estado_anterior = RESULTS_BY_SESSION.get(sid)
    pagina = 1
    empresas_acumuladas = []
    if acao == "carregar_mais" and estado_anterior:
        filtros = estado_anterior["filtros"]
        pagina = estado_anterior["pagina"] + 1
        empresas_acumuladas = estado_anterior["empresas"]

    try:
        empresas, total, _raw = api_client.search(filtros, pagina=pagina)
    except api_client.CasaDosDadosError as exc:
        estado = RESULTS_BY_SESSION.get(sid)
        return render_template("index.html", filtros=filtros, estado=estado, erro=str(exc))

    todas_empresas = empresas_acumuladas + empresas
    colunas, linhas = flatten_records(todas_empresas)

    estado = {
        "filtros": filtros,
        "pagina": pagina,
        "empresas": todas_empresas,
        "linhas": linhas,
        "total": total,
        "colunas": colunas,
        "ultima_pagina_vazia": len(empresas) == 0,
    }
    RESULTS_BY_SESSION[sid] = estado

    return render_template("index.html", filtros=filtros, estado=estado, erro=None)


@app.route("/exportar", methods=["GET"])
def exportar():
    sid = _session_id()
    estado = RESULTS_BY_SESSION.get(sid)
    if not estado or not estado.get("empresas"):
        return render_template("index.html", filtros={}, estado=estado, erro="Nenhum resultado para exportar. Faça uma busca primeiro.")

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
    return render_template("index.html", filtros={}, estado=None, erro=None)


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
