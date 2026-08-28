"""Funções auxiliares: achatar registros JSON aninhados e exportar para XLSX."""
import io

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter


def flatten_record(record, parent_key="", sep="."):
    """Achata um dict aninhado em um único nível, unindo listas simples com ' | '."""
    items = {}
    if isinstance(record, dict):
        for key, value in record.items():
            new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
            items.update(flatten_record(value, new_key, sep))
    elif isinstance(record, list):
        if all(not isinstance(v, (dict, list)) for v in record):
            items[parent_key] = " | ".join(str(v) for v in record if v is not None)
        else:
            for idx, value in enumerate(record):
                items.update(flatten_record(value, f"{parent_key}[{idx}]", sep))
    else:
        items[parent_key] = record
    return items


def flatten_records(records):
    """Achata uma lista de registros e retorna (colunas_ordenadas, linhas_flat)."""
    flat_rows = [flatten_record(r) for r in records]
    colunas = []
    vistas = set()
    for row in flat_rows:
        for key in row.keys():
            if key not in vistas:
                vistas.add(key)
                colunas.append(key)
    return colunas, flat_rows


def build_xlsx(records, sheet_name="Empresas"):
    """Gera um arquivo XLSX em memória a partir de uma lista de registros (dicts)."""
    colunas, flat_rows = flatten_records(records)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_name[:31] or "Empresas"

    ws.append(colunas)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for row in flat_rows:
        ws.append([row.get(col, "") for col in colunas])

    for idx, col in enumerate(colunas, start=1):
        max_len = max([len(col)] + [len(str(row.get(col, ""))) for row in flat_rows]) if flat_rows else len(col)
        ws.column_dimensions[get_column_letter(idx)].width = min(max(max_len + 2, 10), 60)

    ws.freeze_panes = "A2"

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
