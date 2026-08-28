document.addEventListener('DOMContentLoaded', () => {
  const multiSelects = document.querySelectorAll('.multi-select');
  multiSelects.forEach(setupMultiSelect);

  const msUf = document.getElementById('ms-uf');
  const msMunicipio = document.getElementById('ms-municipio');

  if (msUf && msMunicipio) {
    msUf.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener('change', () => {
        atualizarResumo(msUf);
        carregarMunicipios(msUf, msMunicipio);
      });
    });

    if (ufsMarcadas(msUf).length > 0) {
      carregarMunicipios(msUf, msMunicipio);
    } else {
      desabilitarMunicipio(msMunicipio, 'Selecione UF(s) primeiro');
    }
  }
});

function ufsMarcadas(msUf) {
  return Array.from(msUf.querySelectorAll('input[type="checkbox"]:checked')).map((i) => i.value);
}

function desabilitarMunicipio(msMunicipio, texto) {
  const toggle = msMunicipio.querySelector('.ms-toggle');
  toggle.disabled = true;
  msMunicipio.querySelector('.ms-summary').textContent = texto;
  msMunicipio.querySelector('.ms-lista').innerHTML = '';
}

function carregarMunicipios(msUf, msMunicipio) {
  const ufs = ufsMarcadas(msUf);
  const toggle = msMunicipio.querySelector('.ms-toggle');
  const lista = msMunicipio.querySelector('.ms-lista');

  if (ufs.length === 0) {
    desabilitarMunicipio(msMunicipio, 'Selecione UF(s) primeiro');
    return;
  }

  const jaMarcados = new Set(
    Array.from(lista.querySelectorAll('input[type="checkbox"]:checked')).map((i) => i.value)
  );

  toggle.disabled = false;
  lista.innerHTML = '<p class="ms-carregando">Carregando municípios...</p>';

  fetch('/api/municipios?ufs=' + encodeURIComponent(ufs.join(',')))
    .then((resp) => {
      if (!resp.ok) throw new Error('Falha na resposta');
      return resp.json();
    })
    .then((dados) => {
      const nomes = [];
      Object.values(dados).forEach((arr) => nomes.push(...arr));
      nomes.sort((a, b) => a.localeCompare(b, 'pt-BR'));

      lista.innerHTML = '';
      if (nomes.length === 0) {
        lista.innerHTML = '<p class="ms-erro">Não foi possível carregar os municípios agora.</p>';
      }
      nomes.forEach((nome) => {
        const label = document.createElement('label');
        label.className = 'ms-item';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.name = 'municipio';
        checkbox.value = nome;
        checkbox.checked = jaMarcados.has(nome);
        checkbox.addEventListener('change', () => atualizarResumo(msMunicipio));
        label.appendChild(checkbox);
        label.appendChild(document.createTextNode(' ' + nome));
        lista.appendChild(label);
      });

      atualizarResumo(msMunicipio);
      aplicarFiltroTexto(msMunicipio);
    })
    .catch(() => {
      lista.innerHTML = '<p class="ms-erro">Erro ao carregar municípios. Tente novamente.</p>';
    });
}

function setupMultiSelect(container) {
  const toggle = container.querySelector('.ms-toggle');
  const panel = container.querySelector('.ms-panel');
  const filtro = container.querySelector('.ms-filtro');

  toggle.addEventListener('click', () => {
    const estavaFechado = panel.hidden;
    document.querySelectorAll('.ms-panel').forEach((p) => { p.hidden = true; });
    panel.hidden = !estavaFechado;
  });

  document.addEventListener('click', (evento) => {
    if (!container.contains(evento.target)) {
      panel.hidden = true;
    }
  });

  if (filtro) {
    filtro.addEventListener('input', () => aplicarFiltroTexto(container));
  }

  container.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener('change', () => atualizarResumo(container));
  });

  atualizarResumo(container);
}

function aplicarFiltroTexto(container) {
  const filtro = container.querySelector('.ms-filtro');
  if (!filtro) return;
  const termo = filtro.value.trim().toLowerCase();
  container.querySelectorAll('.ms-item').forEach((item) => {
    const texto = item.textContent.trim().toLowerCase();
    item.style.display = texto.includes(termo) ? '' : 'none';
  });
}

function atualizarResumo(container) {
  const campo = container.dataset.campo;
  const marcados = container.querySelectorAll('input[type="checkbox"]:checked');
  const resumo = container.querySelector('.ms-summary');
  const rotulos = { uf: 'UF', municipio: 'Município' };
  const base = rotulos[campo] || campo;

  if (container.querySelector('.ms-toggle').disabled) return;

  resumo.textContent = marcados.length === 0
    ? `Selecione ${base}(s)`
    : `${marcados.length} ${base.toLowerCase()}(s) selecionada(s)`;
}
