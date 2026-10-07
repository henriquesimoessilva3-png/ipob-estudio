/* Estúdio IPOB — o painel. Conversa com painel.py e mostra a prévia ao vivo. */

const $ = id => document.getElementById(id);
let CFG = null;
const VERSAO = "2026-10-06.18";   // tem de bater com painel.py
let FORMATO = "culto";
let VIDEO = null;          // {id, titulo, duracao}
let TAREFA = null;

/* aparência da série: cor, destaque, fundo e tarja. É o que fica gravado
   com o nome da série para a semana seguinte já vir pronta. */
let VISUAL = {};

/* o estudo em uso: série em andamento com visual fixo e episódios numerados.
   null = "novo estudo" (aparência livre, como sempre foi). */
let ESTUDO = null;
let ESTUDOS = [];
let MODO_ESTUDO = "novo";

/* --------------------------------------------------------------- utilidades */
const esc = t => String(t).replace(/[&<>"]/g,
  c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;" }[c]));

const hms = s => {
  s = Math.max(0, Math.round(s));
  const p = n => String(n).padStart(2, "0");
  return `${p(Math.floor(s / 3600))}:${p(Math.floor(s % 3600 / 60))}:${p(s % 60)}`;
};

/* Fora do próprio Estúdio (a cópia pública no GitHub Pages), a página fala
   com o painel pelo endereço que a pessoa informar na faixa de conexão. */
const PUBLICO = !!document.querySelector('meta[name="estudio-publico"]');
const CHAVE_ENDERECO = "estudio-endereco";
function enderecoDoEstudio() {
  if (!PUBLICO) return "";
  try { return (localStorage.getItem(CHAVE_ENDERECO) || "").replace(/\/+$/, ""); } catch (e) { return ""; }
}
function caminho(rota) { return enderecoDoEstudio() + rota; }

async function pedir(rota, corpo) {
  const r = await fetch(caminho(rota), corpo ? {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(corpo),
  } : undefined);
  let d;
  try {
    d = await r.json();
  } catch (e) {
    // HTML no lugar de JSON = o servidor é de uma versão anterior à página:
    // o painel.py mudou e o Flask não recarrega sozinho
    // 405 também: a rota genérica de OPTIONS responde por caminhos que o
    // servidor antigo ainda não conhece
    throw new Error(r.status === 404 || r.status === 405
      ? "O servidor está numa versão antiga e não conhece esta função. " +
        "Feche o painel e abra de novo (o painel.py mudou e o Flask não recarrega sozinho)."
      : `O servidor respondeu com erro ${r.status}. Olhe o Terminal do painel.`);
  }
  if (!r.ok) throw new Error(d.erro || "Falhou.");
  return d;
}

/* Faixa no alto da cópia pública: endereço do Estúdio + estado da conexão */
function montarConexao() {
  if ($("faixaConexao")) return;
  const f = document.createElement("div");
  f.id = "faixaConexao"; f.className = "faixa-conexao";
  f.innerHTML = `
    <img src="assets/logo-redondo.png" alt="">
    <label for="enderecoEstudio">Estúdio</label>
    <input id="enderecoEstudio" placeholder="https://estudio.ipob.org.br" value="${esc(enderecoDoEstudio())}">
    <button id="btConectar" type="button">Conectar</button>
    <span id="estadoConexao"></span>`;
  document.body.prepend(f);
  $("btConectar").onclick = () => {
    try { localStorage.setItem(CHAVE_ENDERECO, $("enderecoEstudio").value.trim()); } catch (e) {}
    location.reload();
  };
  $("enderecoEstudio").addEventListener("keydown", e => { if (e.key === "Enter") $("btConectar").click(); });
}
function marcarConexao(ok) {
  const el = $("estadoConexao"); if (!el) return;
  el.textContent = ok ? "conectado" : (enderecoDoEstudio()
    ? "sem resposta — o computador do Estúdio está ligado e o painel aberto?"
    : "informe o endereço do Estúdio para começar");
  el.className = ok ? "ok" : "falha";
  document.body.classList.toggle("desconectado", !ok);
}

function mostrar(el, sim) { $(el).classList.toggle("oculto", !sim); }
function aviso(alvo, html, classe = "aviso") {
  $(alvo).innerHTML = html ? `<div class="${classe}">${html}</div>` : "";
}

/* ------------------------------------------------------------------- início */
async function iniciar() {
  if (PUBLICO) montarConexao();
  try {
    CFG = await pedir("/api/config");
  } catch (e) {
    if (PUBLICO) { marcarConexao(false); return; }
    throw e;
  }
  if (PUBLICO) marcarConexao(true);
  conferirVersao();

  $("ambiente").innerHTML = CFG._ambiente
    .map(i => i.ok ? `<b>✓</b> ${i.nome}` : `<i>✕ ${i.nome}</i>`)
    .join(" &nbsp; ");

  $("abas").innerHTML = Object.entries(CFG.formatos)
    .map(([k, f]) => `<button data-f="${k}">${f.rotulo}</button>`).join("");
  $("abas").onclick = e => {
    const b = e.target.closest("button");
    if (b) trocarFormato(b.dataset.f);
  };

  $("pregador").innerHTML = Object.entries(CFG.pregadores)
    .map(([k, p]) => `<option value="${k}">${p.longo}</option>`).join("");

  $("pregadoresCapa").innerHTML = Object.entries(CFG.pregadores)
    .map(([k, p]) => `<label><input type="checkbox" value="${k}">
      ${p.longo.replace(/^(Pastor|Presb\.)\s*/, "")}</label>`).join("");

  $("data").value = proximoDomingo();
  VISUAL = { ...CFG.modelos["verde-biblia"], modelo: "verde-biblia",
             tarja_altura: "148", marca: "sim", layout: "classico" };
  trocarFormato("culto");

  ["serie", "episodio", "tema", "referencia"].forEach(id =>
    $(id).addEventListener("input", atualizarPrevia));
  $("pregador").addEventListener("change", atualizarPrevia);
  $("pregadoresCapa").addEventListener("change", atualizarPrevia);

  montarModelos();
  montarLayouts();
  montarFotos();
  montarFundos();
  $("modoEstudo").onclick = e => {
    const b = e.target.closest("button");
    if (b) trocarModoEstudo(b.dataset.modo);
  };
  $("btIniciarEstudo").onclick = iniciarEstudo;
  // o nome do estudo e a série do cartão 3 são a mesma coisa, em dois lugares
  $("nomeEstudo").addEventListener("input", () => {
    $("serie").value = $("nomeEstudo").value;
    aoTrocarSerie();
  });
  $("serie").addEventListener("input", () => { $("nomeEstudo").value = $("serie").value; });
  $("primeiroEpisodio").addEventListener("input", () => {
    $("episodio").value = $("primeiroEpisodio").value;
    atualizarPrevia();
  });
  await carregarEstudos();
  // o formato inicial foi montado antes dos estudos existirem: refaz a escolha
  escolherEstudoDoFormato();
  ["cor", "destaque", "fundo", "tarja_fundo", "tarja_altura", "marca"]
    .forEach(id => $(id).addEventListener("input", () => {
      VISUAL[id] = $(id).value;
      $("modelos").querySelectorAll("button").forEach(b => b.classList.remove("ativa"));
      atualizarPrevia();
    }));
  $("serie").addEventListener("input", aoTrocarSerie);

  $("btAddTrecho").onclick = () => addTrecho();
  $("btSugerir").onclick = sugerirTrechos;
  $("blocoBiblioteca").addEventListener("toggle", e => {
    if (e.target.open) montarBiblioteca();
  });
  $("btShorts").onclick = gerarShorts;

  $("btAnalisar").onclick = analisar;
  $("btConferir").onclick = conferir;
  $("btGravarCorte").onclick = gravarCorte;
  $("btProduzir").onclick = produzir;
  $("btSoShorts").onclick = () => {
    if (!VIDEO) return aviso("erroProduzir", "Analise a transmissão no passo 1 antes.", "erro");
    mostrar("cartaoShorts", true);
    mostrar("shortsSemVideo", !(TAREFA && TAREFA.pasta));
    if (!$("trechos").children.length) addTrecho();
    $("cartaoShorts").scrollIntoView({ behavior: "smooth", block: "start" });
  };
  $("btOutro").onclick = () => location.reload();
  $("btAbrirPasta").onclick = () =>
    pedir("/api/abrir-pasta", { caminho: TAREFA?.pasta });

  $("url").addEventListener("keydown", e => { if (e.key === "Enter") analisar(); });

  travarOQueDependeDoVideo(true);

  dimensionarPrevias();
  addEventListener("resize", () => { dimensionarPrevias(); dimensionarMiniaturas(); });
}

/* Capa e aparência podem ser mexidas a qualquer hora — a prévia está sempre à
   vista. Só o corte e a produção precisam da transmissão analisada, então
   nascem travados em vez de escondidos: assim você enxerga o caminho inteiro. */
let PRODUZINDO = false;

function travarOQueDependeDoVideo(travado) {
  ["inicio", "fim"].forEach(id => { $(id).disabled = travado; });
  // analisar de novo não pode reabilitar o botão no meio de uma renderização:
  // foi assim que saíram dois ffmpeg no mesmo arquivo
  $("btProduzir").disabled = travado || PRODUZINDO;
  $("btSoShorts").disabled = travado;
  if (travado) $("btConferir").disabled = true;
  $("btGravarCorte").disabled = travado;
  $("dicaProduzir").textContent = travado
    ? "Analise a transmissão no passo 1 para liberar a produção."
    : `O vídeo vai para ${CFG._pastas.saida} — fora do Google Drive, ` +
      `para não sincronizar arquivo grande.`;
}

/* --------------------------------------------------------------- versão */
function conferirVersao() {
  // servidor sem versão = anterior a este aviso: também é antigo
  if (CFG._versao === VERSAO) return;
  const faixa = document.createElement("div");
  faixa.className = "faixa-versao";
  faixa.innerHTML = `O programa do painel mudou, mas o servidor ainda é o antigo
    (${esc(CFG._versao || "sem versão")} × ${VERSAO}). As funções novas vão falhar até reiniciar.
    <button id="btReiniciar">Reiniciar o painel agora</button>`;
  document.querySelector("header").after(faixa);
  const clicarReiniciar = async (ev, forcar) => {
    $("btReiniciar").disabled = true;
    $("btReiniciar").textContent = "Reiniciando…";
    try { await pedir("/api/reiniciar", { forcar: !!forcar }); } catch (e) {
      if (!/versão antiga/.test(e.message)) {
        // o servidor respondeu, mas recusou (tarefa rodando): mostra o motivo
        faixa.innerHTML = `${esc(e.message)}
          <button id="btReiniciar">Forçar o reinício agora</button>`;
        $("btReiniciar").onclick = ev2 => clicarReiniciar(ev2, true);
        return;
      }
      // servidor muito antigo (sem esta rota): só resta reiniciar na mão
      faixa.innerHTML = `Este servidor é antigo demais para reiniciar sozinho: feche a
        janela do Terminal do painel (ou Ctrl+C) e abra de novo.`;
      return;
    }
    // espera o servidor novo subir e recarrega
    // sob o launchd a volta leva uns 10 s; a página espera e recarrega
    let tentativas = 0;
    const espera = setInterval(async () => {
      tentativas++;
      try {
        const r = await fetch(caminho("/api/config"), { cache: "no-store" });
        if (r.ok) {
          const c = await r.json();
          if (c._versao === VERSAO) { clearInterval(espera); location.reload(); return; }
        }
      } catch (e) {}
      if (tentativas > 45) {
        clearInterval(espera);
        faixa.innerHTML = "O painel não voltou. Abra o <b>Abrir Estúdio IPOB.command</b> na pasta estudio.";
      }
    }, 1000);
  };
  $("btReiniciar").onclick = ev => clicarReiniciar(ev, false);
}

/* ------------------------------------------------------------- aparência */
function layoutsDoFormato() {
  const todos = (CFG.layouts || {})[FORMATO] || { classico: { nome: "Clássico" } };
  return Object.fromEntries(Object.entries(todos).filter(([k]) => !k.startsWith("_")));
}

function montarLayouts() {
  const lista = layoutsDoFormato();
  if (!lista[VISUAL.layout]) VISUAL.layout = "classico";

  $("layouts").innerHTML = Object.entries(lista).map(([k, l]) => `
    <button data-l="${k}" title="${l.descricao || l.nome}">
      <span class="mini"><iframe data-layout="${k}" tabindex="-1"></iframe></span>
      <span class="rotulo">${l.nome}</span>
    </button>`).join("");

  $("layouts").onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    VISUAL.layout = b.dataset.l;
    marcarLayout();
    atualizarPrevia();
  };
  marcarLayout();
  dimensionarMiniaturas();
}

function marcarLayout() {
  const lista = layoutsDoFormato();
  $("layouts").querySelectorAll("button").forEach(b =>
    b.classList.toggle("ativa", b.dataset.l === (VISUAL.layout || "classico")));
  const l = lista[VISUAL.layout || "classico"];
  $("layoutDescricao").textContent = l ? (l.descricao || "") : "";
}

function dimensionarMiniaturas() {
  document.querySelectorAll(".layouts .mini").forEach(m => {
    const escala = m.clientWidth / 1920;
    m.querySelector("iframe").style.transform = `scale(${escala})`;
  });
}

/* pregadores com mais de uma foto: um seletor para cada */
function montarFotos() {
  const com = Object.entries(CFG.pregadores).filter(([, p]) => (p.fotos || []).length > 1);
  $("linhaFotos").innerHTML = com.map(([k, p]) => `
    <div class="campo">
      <label for="foto_${k}">Foto · ${esc(p.longo.replace(/^(Pastor|Presb\.)\s*/, ""))}</label>
      <select id="foto_${k}" data-pregador="${k}">
        ${p.fotos.map(f => `<option value="${f.id}">${esc(f.nome)}</option>`).join("")}
      </select>
    </div>`).join("");
  mostrar("linhaFotos", com.length > 0);
  $("linhaFotos").querySelectorAll("select").forEach(s => s.addEventListener("change", () => {
    VISUAL.fotos = fotosEscolhidas();
    atualizarPrevia();
  }));
}

function fotosEscolhidas() {
  return [...$("linhaFotos").querySelectorAll("select")]
    .map(s => `${s.dataset.pregador}:${s.value}`).join(",");
}

function escreverFotos() {
  const esc_ = Object.fromEntries((VISUAL.fotos || "").split(",").filter(Boolean).map(x => x.split(":")));
  $("linhaFotos").querySelectorAll("select").forEach(s => {
    if (esc_[s.dataset.pregador]) s.value = esc_[s.dataset.pregador];
    else s.selectedIndex = 0;
  });
}

function montarModelos() {
  $("modelos").innerHTML = Object.entries(CFG.modelos).map(([k, m]) => `
    <button data-m="${k}" title="${m.nome}">
      <span class="amostra" style="background:${m.cor}">
        <span class="textura" style="background-image:url('assets/fundos/${m.fundo}')"></span>
        <i style="background:${m.destaque}"></i>
      </span>
      <span class="rotulo">${m.nome}</span>
    </button>`).join("");

  $("modelos").onclick = e => {
    const b = e.target.closest("button");
    if (!b) return;
    aplicarModelo(b.dataset.m);
    $("modelos").querySelectorAll("button").forEach(x =>
      x.classList.toggle("ativa", x === b));
  };
}

function montarFundos() {
  const nomes = {
    "biblia.jpg": "Bíblia aberta", "luz.jpg": "Luz", "ondas.jpg": "Ondas",
    "vitral.jpg": "Vitral", "bruma.jpg": "Bruma", "liso.jpg": "Liso (sem foto)",
  };
  $("fundo").innerHTML = (CFG._fundos || []).map(f =>
    `<option value="${f}">${nomes[f] || f}</option>`).join("");
}

function aplicarModelo(chave) {
  const m = CFG.modelos[chave];
  if (!m) return;
  VISUAL = {
    modelo: chave, cor: m.cor, destaque: m.destaque, fundo: m.fundo,
    tarja_fundo: m.tarja_fundo, tarja_altura: VISUAL.tarja_altura || "148",
    marca: VISUAL.marca || "sim", layout: VISUAL.layout || "classico",
  };
  escreverVisual();
  atualizarPrevia();
}

function escreverVisual() {
  ["cor", "destaque", "fundo", "tarja_fundo", "marca"].forEach(id => {
    if (VISUAL[id] != null) $(id).value = VISUAL[id];
  });
  $("tarja_altura").value = parseInt(VISUAL.tarja_altura || 148, 10);
  $("modelos").querySelectorAll("button").forEach(b =>
    b.classList.toggle("ativa", b.dataset.m === VISUAL.modelo));
  if (!VISUAL.layout) VISUAL.layout = "classico";
  marcarLayout();
  escreverFotos();
}

/* a série ditou o visual: se já existe, recupera; se é nova, sugere modelos */
function aoTrocarSerie() {
  if (ESTUDO) return;                      // a série é a do estudo
  const nome = $("serie").value.trim().toUpperCase();
  const salva = CFG.series_salvas[nome];

  if (salva) {
    VISUAL = { ...salva };
    escreverVisual();
    aviso("avisoSerie",
      `Série conhecida: recuperei as cores que você usou da última vez.`, "achado");
  } else if (nome) {
    aviso("avisoSerie",
      `<b>Série nova.</b> Escolha um modelo abaixo — ele define a cor de tudo:
       capa, plaquinhas, tingimento da foto e a barra da tarja. Depois dá para
       ajustar cada cor na mão.`, "serie-nova");
  } else {
    aviso("avisoSerie", "");
  }
  atualizarPrevia();
}

function proximoDomingo() {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay());          // domingo desta semana
  return d.toISOString().slice(0, 10);
}

function trocarFormato(k) {
  FORMATO = k;
  const f = CFG.formatos[k];
  [...$("abas").children].forEach(b =>
    b.classList.toggle("ativa", b.dataset.f === k));

  $("serie").value = f.serie;
  $("episodio").value = f.proximo_episodio;
  $("rotuloRef").textContent =
    k === "ebd" ? "Capítulo / referência" : "Referência bíblica";
  $("referencia").placeholder = k === "ebd" ? "CAPÍTULO 16" : "Amós 9. 1-10";

  const naCapa = f.pregadores_na_capa || [];
  $("pregadoresCapa").querySelectorAll("input").forEach(i =>
    i.checked = naCapa.includes(i.value));
  mostrar("campoCapa", k === "culto");

  montarLayouts();
  aoTrocarSerie();
  if (ESTUDOS.length || ESTUDO) escolherEstudoDoFormato();
}

/* ============================================================== estudos */
async function carregarEstudos() {
  try {
    ESTUDOS = (await pedir("/api/estudos")).estudos || [];
  } catch (e) { ESTUDOS = []; }
}

function estudoAtivoDoFormato() {
  return ESTUDOS.find(e => e.formato === FORMATO && !e.fim) || null;
}

/* ao abrir o painel ou trocar de aba: se há estudo em andamento, continua nele */
function escolherEstudoDoFormato() {
  const ativo = estudoAtivoDoFormato();
  if (ativo) { usarEstudo(ativo); trocarModoEstudo("existente", true); }
  else { ESTUDO = null; trocarModoEstudo("novo", true); }
}

function trocarModoEstudo(modo, silencioso = false) {
  MODO_ESTUDO = modo;
  $("modoEstudo").querySelectorAll("button").forEach(b =>
    b.classList.toggle("ativa", b.dataset.modo === modo));
  if (modo === "existente") {
    montarListaEstudos();
    mostrar("painelEstudos", !ESTUDO);
    mostrar("estudoAtual", !!ESTUDO);
    mostrar("aparenciaCompleta", false);
  } else {
    if (!silencioso) soltarEstudo();
    mostrar("painelEstudos", false);
    mostrar("estudoAtual", false);
    mostrar("aparenciaCompleta", true);
    mostrar("blocoIniciar", true);
    mostrar("blocoSalvarVisual", false);
    mostrar("linhaNomeEstudo", true);
    $("nomeEstudo").value = $("serie").value;
    $("primeiroEpisodio").value = $("episodio").value || 1;
    dimensionarMiniaturas();
  }
}

function montarListaEstudos() {
  const d = dadosDaArte();
  // todos os estudos, dos dois formatos: clicar num de outro formato troca a aba
  const meus = ESTUDOS.slice();
  const ativos = meus.filter(e => !e.fim);
  const antigos = meus.filter(e => e.fim).reverse();
  const rotuloFormato = f => (CFG.formatos[f] || {}).rotulo?.split(" — ")[0] || f;
  const item = e => {
    const v = e.visual || {};
    const q = new URLSearchParams({ ...d, tipo: "capa", formato: e.formato, serie: e.serie,
      ep: e.proximo, layout: v.layout || "classico", cor: v.cor || "", destaque: v.destaque || "",
      fundo: v.fundo || "", marca: v.marca || "sim", pregador: e.pregador || "", fotos: v.fotos || "",
      pregadores: (e.pregadores_na_capa || []).join(","),
      tema: (e.episodios || []).slice(-1)[0]?.tema || "Tema da mensagem" });
    const feitos = (e.episodios || []).length;
    return `
      <button class="estudo-item ${e.fim ? "encerrado" : ""}" data-id="${e.id}">
        <span class="mini"><iframe src="${caminho("/artes/arte.html")}?${q}" tabindex="-1"></iframe></span>
        <span class="texto"><b>${esc(e.serie)} <i class="etiqueta-formato">${esc(rotuloFormato(e.formato))}</i></b>
          <span>${feitos} episódio${feitos === 1 ? "" : "s"} · próximo: ${e.proximo}
          ${e.fim ? ` · encerrado em ${dataBr(e.fim)}` : ` · desde ${dataBr(e.inicio)}`}</span></span>
        ${e.fim && !ativos.some(a => a.formato === e.formato) ? `<span class="reabrir" data-reabrir="${e.id}">Reabrir</span>` : ""}
      </button>`;
  };
  $("listaEstudos").innerHTML =
    (ativos.length ? `<h4>Em andamento</h4>` + ativos.map(item).join("") : "") +
    (antigos.length ? `<h4>Encerrados</h4>` + antigos.map(item).join("") : "") +
    (!meus.length ? `<div class="vazio">Nenhum estudo gravado ainda.
       Use <b>Novo estudo</b>, escolha a aparência e clique em
       <b>Iniciar estudo</b>.</div>` : "");
  $("listaEstudos").querySelectorAll(".mini").forEach(m => {
    m.querySelector("iframe").style.transform = `scale(${128 / 1920})`;
  });
  $("listaEstudos").onclick = async ev => {
    const r = ev.target.closest("[data-reabrir]");
    if (r) {
      ev.stopPropagation();
      try {
        await pedir(`/api/estudos/${r.dataset.reabrir}/reabrir`, {});
        await carregarEstudos();
        const e = ESTUDOS.find(x => x.id === r.dataset.reabrir);
        if (e.formato !== FORMATO) trocarFormato(e.formato);
        usarEstudo(e);
        trocarModoEstudo("existente", true);
      } catch (e) { aviso("avisoSerie", e.message, "erro"); }
      return;
    }
    const b = ev.target.closest(".estudo-item");
    if (!b) return;
    const e = ESTUDOS.find(x => x.id === b.dataset.id);
    if (!e) return;
    if (e.formato !== FORMATO) trocarFormato(e.formato);   // o estudo manda na aba
    usarEstudo(e); trocarModoEstudo("existente", true);
  };
}

function dataBr(iso) {
  if (!iso) return "";
  const [a, m, d] = iso.split("-");
  return `${d}/${m}/${a}`;
}

/* aplica o estudo nos campos: série travada, episódio seguinte, visual dele */
function usarEstudo(e) {
  ESTUDO = e;
  $("serie").value = e.serie;
  $("serie").readOnly = true;
  $("episodio").value = e.proximo;
  if (e.pregador) $("pregador").value = e.pregador;
  const naCapa = e.pregadores_na_capa || [];
  if (naCapa.length) $("pregadoresCapa").querySelectorAll("input").forEach(i =>
    i.checked = naCapa.includes(i.value));
  // um estudo gravado com visual incompleto cai nos padrões do primeiro modelo
  VISUAL = { ...CFG.modelos["verde-biblia"], modelo: "verde-biblia", tarja_altura: "148",
             marca: "sim", layout: "classico", ...(e.visual || {}) };
  escreverVisual();
  mostrarEstudoAtual();
  atualizarPrevia();
}

function soltarEstudo() {
  ESTUDO = null;
  $("serie").readOnly = false;
  $("serie").value = "";
  $("nomeEstudo").value = "";
  $("episodio").value = 1;
  $("primeiroEpisodio").value = 1;
  $("nomeEstudo").focus();
  aviso("avisoSerie", `<b>Novo estudo.</b> Dê o nome da série, escolha layout e cores
    e clique em <b>Iniciar estudo</b> no fim deste cartão.`, "serie-nova");
  atualizarPrevia();
}

function mostrarEstudoAtual() {
  const e = ESTUDO;
  if (!e) return;
  const eps = (e.episodios || []);
  const l = (CFG.layouts?.[e.formato]?.[e.visual?.layout] || {}).nome || e.visual?.layout || "";
  $("estudoAtual").innerHTML = `
    <div class="estudo-atual">
      <div class="cabeca">
        <div><b>${esc(e.serie)}</b>
          <span class="dica" style="margin:0 0 0 8px">${l ? `layout ${esc(l)} · ` : ""}
          ${e.fim ? `encerrado em ${dataBr(e.fim)}` : `desde ${dataBr(e.inicio)}`}</span></div>
        <div class="acoes">
          <button id="btTrocarEstudo">Trocar</button>
          <button id="btAjustarVisual">Ajustar aparência</button>
          ${e.fim ? `<button id="btReabrirEstudo">Reabrir</button>`
                  : `<button id="btEncerrarEstudo">Encerrar estudo</button>`}
        </div>
      </div>
      <div class="linha-tempo">
        ${eps.map(x => `<span title="${esc(x.tema || "")}" data-n="${esc(x.n)}" data-pasta="${esc(x.pasta || "")}" class="episodio"><span class="rotulo"><b>${esc(x.n)}</b> · ${esc(x.tema || "")}</span>
          <button class="tirar-ep" data-n="${esc(x.n)}" title="Tirar este episódio do estudo" aria-label="Tirar do estudo">×</button></span>`).join("")}
        ${e.fim ? "" : `<span class="proximo"><b>${esc(e.proximo)}</b> · este</span>`}
      </div>
      <div id="detalheEpisodio" class="detalhe-episodio oculto"></div>
    </div>`;
  // clicar num episódio abre o que já foi produzido para ele
  $("estudoAtual").querySelectorAll(".linha-tempo span.episodio .rotulo").forEach(r => {
    r.style.cursor = "pointer";
    r.onclick = () => { const sp = r.closest("span.episodio"); mostrarEpisodio(sp.dataset.pasta, eps.find(x => String(x.n) === sp.dataset.n)); };
  });
  // apagar em dois toques: o primeiro pergunta, o segundo apaga
  $("estudoAtual").querySelectorAll(".tirar-ep").forEach(b => {
    b.onclick = async ev => {
      ev.stopPropagation();
      const pill = b.closest("span");
      if (!pill.classList.contains("confirmando")) {
        $("estudoAtual").querySelectorAll(".confirmando").forEach(p => {
          p.classList.remove("confirmando"); p.querySelector(".pergunta")?.remove();
        });
        pill.classList.add("confirmando");
        pill.insertAdjacentHTML("afterbegin", `<i class="pergunta">Apagar o episódio ${esc(b.dataset.n)}? Toque de novo para apagar.</i>`);
        pill.onclick = ev2 => { if (ev2.target !== b) b.click(); };
        return;
      }
      b.disabled = true;
      try {
        const r = await pedir(`/api/estudos/${e.id}/episodios/${encodeURIComponent(b.dataset.n)}/remover`, {});
        await carregarEstudos();
        ESTUDO = ESTUDOS.find(x => x.id === e.id) || r.estudo;
        mostrarEstudoAtual();
        if ($("episodio")) { $("episodio").value = ESTUDO.proximo; }
      } catch (err) { aviso("avisoSerie", esc(err.message), "erro"); b.disabled = false; }
    };
  });
  $("btTrocarEstudo").onclick = () => { ESTUDO = null; $("serie").readOnly = false; aviso("avisoEstudo", "");
    mostrar("estudoAtual", false); montarListaEstudos(); mostrar("painelEstudos", true); };
  $("btAjustarVisual").onclick = () => {
    const ab = $("aparenciaCompleta").classList.contains("oculto");
    mostrar("aparenciaCompleta", ab);
    mostrar("blocoIniciar", false);
    mostrar("linhaNomeEstudo", false);
    mostrar("blocoSalvarVisual", ab);
    $("btAjustarVisual").textContent = ab ? "Esconder aparência" : "Ajustar aparência";
    if (ab) { dimensionarMiniaturas(); atualizarPrevia(); }
  };
  $("btSalvarVisual").onclick = async () => {
    const d = dadosDaArte();
    const b = $("btSalvarVisual"); b.disabled = true;
    try {
      const r = await pedir(`/api/estudos/${e.id}/visual`, {
        visual: { ...VISUAL },
        pregador: d.pregador,
        pregadores_na_capa: d.pregadores.split(",").filter(Boolean),
      });
      await carregarEstudos();
      ESTUDO = ESTUDOS.find(x => x.id === e.id) || r.estudo;
      aviso("avisoSalvarVisual", `Aparência do estudo <b>${esc(e.serie)}</b> salva.`, "achado");
      const l = (CFG.layouts?.[e.formato]?.[VISUAL.layout] || {}).nome || VISUAL.layout;
      $("estudoAtual").querySelector(".cabeca .dica").innerHTML =
        `${l ? `layout ${esc(l)} · ` : ""}desde ${dataBr(e.inicio)}`;
    } catch (err) {
      aviso("avisoSalvarVisual", err.message, "erro");
    } finally { b.disabled = false; }
  };
  const enc = $("btEncerrarEstudo");
  if (enc) enc.onclick = async () => {
    try {
      await pedir(`/api/estudos/${e.id}/encerrar`, {});
      await carregarEstudos();
      ESTUDO = null; $("serie").readOnly = false;
      trocarModoEstudo("novo");
      aviso("avisoSerie", `Estudo <b>${esc(e.serie)}</b> encerrado. Quando quiser,
        inicie o próximo aqui.`, "achado");
    } catch (err) { aviso("avisoSerie", err.message, "erro"); }
  };
  const rea = $("btReabrirEstudo");
  if (rea) rea.onclick = async () => {
    try {
      await pedir(`/api/estudos/${e.id}/reabrir`, {});
      await carregarEstudos();
      usarEstudo(ESTUDOS.find(x => x.id === e.id));
    } catch (err) { aviso("avisoSerie", err.message, "erro"); }
  };
  mostrar("blocoIniciar", false);
}

async function iniciarEstudo() {
  const d = dadosDaArte();
  const b = $("btIniciarEstudo");
  if (!$("serie").value.trim()) {
    $("nomeEstudo").focus();
    return aviso("avisoIniciar", "Dê um nome ao estudo antes de iniciar.", "erro");
  }
  b.disabled = true; b.textContent = "Gravando…";
  try {
    const r = await pedir("/api/estudos", {
      formato: FORMATO,
      serie: $("serie").value.trim(),
      playlist: $("serie").value.trim().toUpperCase(),
      pregador: d.pregador,
      pregadores_na_capa: d.pregadores.split(",").filter(Boolean),
      primeiro_episodio: parseInt($("primeiroEpisodio").value, 10) || parseInt($("episodio").value, 10) || 1,
      visual: { ...VISUAL },
    });
    await carregarEstudos();
    usarEstudo(r.estudo);
    trocarModoEstudo("existente", true);
    aviso("avisoIniciar", "");
    // o estudo novo aparece como "Estudo existente": avisa o que aconteceu
    const e = r.estudo;
    const rotulo = (CFG.formatos[e.formato] || {}).rotulo?.split(" — ")[0] || e.formato;
    aviso("avisoEstudo",
      `Estudo <b>${esc(e.serie)}</b> (${esc(rotulo)}) criado com esta aparência. ` +
      `Este vídeo será o episódio <b>${esc(e.proximo)}</b>; os próximos seguem a sequência. ` +
      `Para mudar cores ou layout depois, use <b>Ajustar aparência</b>.`, "achado");
    $("estudoAtual").scrollIntoView({ behavior: "smooth", block: "center" });
  } catch (e) {
    aviso("avisoIniciar", e.message, "erro");
    $("avisoIniciar").scrollIntoView({ behavior: "smooth", block: "center" });
  } finally {
    b.disabled = false; b.textContent = "Iniciar estudo com esta aparência";
  }
}

/* ------------------------------------------------ detalhe de um episódio */
async function mostrarEpisodio(pasta, ep) {
  const caixa = $("detalheEpisodio");
  if (!caixa) return;
  if (caixa.dataset.pasta === pasta && !caixa.classList.contains("oculto")) {
    mostrar("detalheEpisodio", false); return;
  }
  caixa.dataset.pasta = pasta;
  caixa.innerHTML = `<p class="dica">Procurando o que já existe deste episódio…</p>`;
  mostrar("detalheEpisodio", true);
  let d;
  try {
    d = await pedir("/api/episodio?pasta=" + encodeURIComponent(pasta));
  } catch (e) {
    caixa.innerHTML = `
      <div class="cabeca"><b>${esc(ep?.n)} · ${esc(ep?.tema || "")}</b>
        <button id="btFecharEp">Fechar</button></div>
      <p class="dica">${esc(e.message)} Nada produzido ainda para este episódio.</p>`;
    $("btFecharEp").onclick = () => mostrar("detalheEpisodio", false);
    return;
  }
  const f = d.ficha || {};
  const q = encodeURIComponent(pasta);
  const seg = s => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  caixa.innerHTML = `
    <div class="cabeca">
      <b>${esc(ep?.n || f.episodio)} · ${esc(f.tema || ep?.tema || "")}</b>
      <div class="acoes">
        <button id="btPastaEp">Abrir pasta</button>
        <button id="btRetomarEp">Retomar no painel</button>
        <button id="btFecharEp">Fechar</button>
      </div>
    </div>
    <div class="corpo">
      ${d.capa ? `<img class="capa-ep" src="${caminho("/api/arquivo")}?pasta=${q}&nome=capa.jpg" alt="">` : ""}
      <div class="itens">
        <div><span>Data</span>${esc(f.data || ep?.data || "—")}</div>
        <div><span>Referência</span>${esc(f.referencia || ep?.referencia || "—")}</div>
        <div><span>Pregador</span>${esc(((CFG.pregadores || {})[f.pregador] || {}).curto?.replace(/\n/g, " ") || f.pregador || "—")}</div>
        <div><span>Corte</span>${f.inicio ? `${esc(f.inicio)} → ${esc(f.fim || "")}` : "—"}</div>
        <div><span>Vídeo</span>${d.video ? `${esc(d.video.nome)} · ${d.video.mb} MB` : "ainda não produzido"}</div>
        <div><span>Shorts</span>${d.shorts.length ? d.shorts.map(s => `${esc(s.nome)} (${seg(s.segundos)})`).join(", ") : "nenhum"}</div>
        <div><span>Legenda</span>${d.legenda ? "legenda.srt" : "—"}</div>
        <div><span>YouTube</span>${f.youtube ? `<a href="${esc(f.youtube)}" target="_blank" rel="noopener">${esc(f.youtube)}</a>` : "ainda não subiu"}</div>
        <div><span>Pasta</span><code>${esc(pasta)}</code></div>
      </div>
    </div>`;
  $("btFecharEp").onclick = () => mostrar("detalheEpisodio", false);
  $("btPastaEp").onclick = () => pedir("/api/abrir-pasta", { caminho: pasta });
  $("btRetomarEp").onclick = ev => abrirProducao({ pasta, url: f.url, arquivo: d.video ? pasta + "/" + d.video.nome : "" }, ev.target);
}

/* ------------------------------------------------------------ gravar corte */
async function gravarCorte() {
  if (!VIDEO) return;
  const b = $("btGravarCorte");
  b.disabled = true;
  try {
    const r = await pedir("/api/corte", {
      video_id: VIDEO.id, formato: FORMATO, duracao: VIDEO.duracao,
      inicio: $("inicio").value, fim: $("fim").value,
    });
    const a = r.aprendeu || {};
    aviso("avisoCorte",
      `Corte gravado: <b>${r.corte.inicio_texto}</b> → <b>${r.corte.fim_texto}</b>.` +
      (a.centro ? ` O aprendizado do ${FORMATO} agora tem ${a.cortes} cortes e espera a
        pregação por volta de ${Math.round(a.centro * 100)}% da transmissão.` : ""),
      "achado");
  } catch (e) {
    aviso("avisoCorte", e.message, "erro");
  } finally {
    b.disabled = false;
  }
}

/* ------------------------------------------------------------------ prévias */
function dadosDaArte() {
  const marcados = [...$("pregadoresCapa").querySelectorAll("input:checked")]
    .map(i => i.value);
  return {
    formato: FORMATO,
    serie: $("serie").value || "SÉRIE",
    ep: $("episodio").value,
    tema: $("tema").value || "Tema da mensagem",
    ref: $("referencia").value,
    badge: CFG.formatos[FORMATO].prefixo_badge || "",
    pregador: $("pregador").value,
    pregadores: marcados.join(","),
    cor: VISUAL.cor || "",
    destaque: VISUAL.destaque || "",
    fundo: VISUAL.fundo || "",
    marca: VISUAL.marca || "sim",
    layout: VISUAL.layout || "classico",
    fotos: VISUAL.fotos || "",
    vars: [
      VISUAL.tarja_fundo ? `--tarja-fundo:${VISUAL.tarja_fundo}` : "",
      VISUAL.tarja_altura ? `--tarja-altura:${VISUAL.tarja_altura}px` : "",
    ].filter(Boolean).join(";"),
  };
}

let relogioPrevia = null;
function atualizarPrevia() {
  clearTimeout(relogioPrevia);
  relogioPrevia = setTimeout(() => {
    const d = dadosDaArte();
    const q = t => caminho("/artes/arte.html") + "?" + new URLSearchParams({ ...d, tipo: t });
    $("previaCapa").src = q("capa");
    $("previaTarja").src = q("tarja");
    // as miniaturas da galeria mostram os mesmos dados, um layout em cada
    document.querySelectorAll(".layouts iframe").forEach(f => {
      f.src = caminho("/artes/arte.html") + "?" + new URLSearchParams(
        { ...d, tipo: "capa", layout: f.dataset.layout });
    });
  }, 220);
}

function dimensionarPrevias() {
  document.querySelectorAll(".moldura").forEach(m => {
    const escala = m.clientWidth / 1920;
    m.querySelector("iframe").style.transform = `scale(${escala})`;
  });
}

/* ----------------------------------------------------------------- analisar */
async function analisar() {
  const url = $("url").value.trim();
  if (!url) return aviso("avisoAnalise", "Cole o link da transmissão.", "erro");

  $("btAnalisar").disabled = true;
  $("btAnalisar").textContent = "Lendo a transmissão…";
  aviso("avisoAnalise", "");

  try {
    const r = await pedir("/api/analisar", { url, formato: FORMATO });
    VIDEO = r.info;

    $("resumoVideo").innerHTML =
      `<b>${r.info.titulo}</b><br>Transmissão de ${r.duracao_texto}` +
      (r.blocos ? ` · ${r.blocos} trechos de transcrição lidos.` : ".");

    $("inicio").value = r.inicio_texto;
    $("fim").value = r.fim_texto;

    if (r.sem_transcricao && r.pode_transcrever) {
      aviso("achado",
        `<b>Esta transmissão ainda não tem transcrição automática no YouTube.</b>
         Ela costuma aparecer algumas horas depois que a live termina.<br><br>
         Sem esse texto o Estúdio não tem como achar o começo da pregação
         sozinho — os campos abaixo estão só com a metade da transmissão, que
         não é palpite de verdade. Duas saídas: abrir o vídeo e digitar o tempo,
         ou mandar transcrever aqui na máquina.<br><br>
         <button class="acao" id="btTranscrever">Transcrever aqui na máquina</button>
         <span class="dica" style="margin-left:10px">baixa o áudio e transcreve;
         alguns minutos, e na primeira vez baixa o modelo</span>`, "aviso");
      $("btTranscrever").onclick = transcreverLocal;
      $("btConferir").disabled = true;
    } else if (r.sem_transcricao) {
      // sem texto não há o que procurar: o palpite é só a metade da transmissão
      aviso("achado",
        `<b>Esta transmissão ainda não tem transcrição automática no YouTube.</b>
         Ela costuma aparecer algumas horas depois que a live termina — em
         transmissões antigas do canal já está lá.<br><br>
         Sem esse texto o Estúdio não tem como achar o começo da pregação
         sozinho. O <b>${r.inicio_texto}</b> nos campos abaixo é só a metade da
         transmissão, não um palpite de verdade: abra o vídeo, veja onde a
         pregação começa e digite o tempo. O resto — corte, capa, tarja, título
         e descrição — funciona normalmente.`, "aviso");
    } else if (r.gravado) {
      aviso("achado",
        `Corte <b>gravado por você</b> em ${r.gravado.replace("T", " às ")}:
         <b>${r.inicio_texto}</b> → <b>${r.fim_texto}</b>. É ele que vale; para
         mudar, ajuste os campos e grave de novo.`, "achado");
    } else if (r.achou) {
      aviso("achado",
        `Achei o começo em <b>${r.inicio_texto}</b> — reconheci
         “${r.motivo}”.<q>“…${r.trecho}…”</q>
         Confira com <b>Ouvir o trecho</b> antes de produzir.`, "achado");
    } else {
      aviso("achado",
        `Li a transcrição, mas não achei uma frase clara de abertura da Palavra.
         O <b>${r.inicio_texto}</b> é só a metade da transmissão — use
         <b>Ouvir o trecho</b> para se localizar e ajuste na mão.`, "aviso");
    }

    // sem transcrição, "Ouvir o trecho" não tem o que mostrar
    $("btConferir").disabled = !r.blocos;

    $("alternativas").innerHTML = (r.alternativas || [])
      .map(a => `<button data-t="${a.segundos}">${a.texto} · ${a.motivo}</button>`)
      .join("");
    $("alternativas").onclick = e => {
      const b = e.target.closest("button");
      if (b) { $("inicio").value = hms(+b.dataset.t); conferir(); }
    };

    travarOQueDependeDoVideo(false);
    mostrarFonte(r.fonte);
    $("cartaoCorte").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) {
    aviso("avisoAnalise", e.message, "erro");
  } finally {
    $("btAnalisar").disabled = false;
    $("btAnalisar").textContent = "Analisar transmissão";
  }
}

async function conferir() {
  if (!VIDEO) return;
  const seg = paraSegundos($("inicio").value);
  const r = await pedir("/api/conferir", { video_id: VIDEO.id, segundos: seg });
  $("transcricao").innerHTML = r.linhas.length
    ? r.linhas.map(l => `<div><b>${l.tempo}</b><span>${l.texto}</span></div>`).join("")
    : "<div>Sem transcrição nesse ponto.</div>";
  mostrar("transcricao", true);
}

function paraSegundos(t) {
  return String(t).split(":").reduce((a, x) => a * 60 + (parseFloat(x) || 0), 0);
}

/* ----------------------------------------------------------------- produzir */
async function produzir() {
  if (!VIDEO) return;
  if (!$("tema").value.trim())
    return aviso("erroProduzir", "Escreva o tema — ele vai na capa e no título.", "erro");

  aviso("erroProduzir", "");
  PRODUZINDO = true;
  $("btProduzir").disabled = true;
  mostrar("andamento", true);

  const d = dadosDaArte();
  let r;
  try {
    r = await pedir("/api/produzir", {
    url: $("url").value.trim(),
    video_id: VIDEO.id,
    formato: FORMATO,
    serie: d.serie,
    episodio: d.ep,
    tema: d.tema,
    referencia: d.ref,
    pregador: d.pregador,
    pregadores_na_capa: d.pregadores.split(",").filter(Boolean),
    inicio: $("inicio").value,
    fim: $("fim").value,
    data: $("data").value,
      visual: { ...VISUAL, vars: d.vars },
      estudo_id: ESTUDO ? ESTUDO.id : "",
    });
  } catch (e) {
    PRODUZINDO = false;
    $("btProduzir").disabled = false;
    mostrar("andamento", false);
    return aviso("erroProduzir", e.message, "erro");
  }

  acompanhar(r.tarefa);
}

async function pararTarefa(tid, botao) {
  botao.disabled = true; botao.textContent = "Parando…";
  try { await pedir(`/api/tarefa/${tid}/parar`, {}); }
  catch (e) { botao.disabled = false; botao.textContent = "Parar"; }
}

function acompanhar(tid) {
  $("btParar").disabled = false; $("btParar").textContent = "Parar a produção";
  $("btParar").onclick = () => pararTarefa(tid, $("btParar"));
  const relogio = setInterval(async () => {
    const t = await pedir(`/api/tarefa/${tid}`);
    TAREFA = t;
    $("barraProgresso").style.width = (t.progresso * 100) + "%";
    $("etapa").textContent = t.etapa || "";
    $("detalhe").textContent = t.detalhe || "";
    $("registro").innerHTML = (t.log || []).slice(-14).join("<br>");
    $("registro").scrollTop = 1e6;

    if (t.estado === "pronto") {
      clearInterval(relogio);
      PRODUZINDO = false;
      mostrar("andamento", false);
      mostrar("pronto", true);
      mostrar("cartaoShorts", true);
      mostrar("shortsSemVideo", false);
      if (!$("trechos").children.length) addTrecho();
      prepararYoutube();
      $("prontoArquivo").innerHTML =
        `<b>${t.arquivo.split("/").pop()}</b> — ${t.tamanho_mb} MB<br>
         Na mesma pasta: <b>capa.jpg</b> (miniatura),
         <b>titulo e descricao.txt</b>` +
        (t.legendas ? `, <b>legenda.srt</b> (${t.legendas} legendas)` : "") + `.
         <div class="onde"><span>Tudo em</span><code>${esc(t.pasta)}</code></div>`;
      $("prontoTitulo").innerHTML =
        `Título: <b>${t.titulo}</b>` +
        (t.playlist ? `<br>Playlist: <b>${t.playlist}</b>` : "");
      // o episódio entrou na linha do tempo do estudo
      if (ESTUDO) carregarEstudos().then(() => {
        const e = ESTUDOS.find(x => x.id === ESTUDO.id);
        if (e) { ESTUDO = e; mostrarEstudoAtual(); }
      });
    }
    if (t.estado === "erro") {
      clearInterval(relogio);
      PRODUZINDO = false;
      mostrar("andamento", false);
      $("btProduzir").disabled = false;
      aviso("erroProduzir", t.erro, "erro");
    }
  }, 900);
}

iniciar();


/* ==========================================================================
   Subir para o YouTube — só acontece quando você clica.
   ========================================================================== */
async function prepararYoutube() {
  const e = await pedir("/api/youtube/estado");

  if (!e.configurado) {
    $("ytEstado").innerHTML = `
      <div class="aviso">
        Ainda não está ligado. É uma configuração de uma vez só, feita por você
        na sua conta Google — eu não consigo criar a credencial no seu lugar.
      </div>
      <details class="ajuda">
        <summary>Como ligar (uma vez só)</summary>
        <ol class="passos">
          <li>Abra <b>console.cloud.google.com</b> com a conta do canal e crie
              um projeto.</li>
          <li>Em <b>APIs e serviços → Biblioteca</b>, ative a
              <b>YouTube Data API v3</b>.</li>
          <li>Em <b>Tela de permissão OAuth</b> (nos projetos novos aparece
              como <b>Google Auth Platform</b>), escolha <b>Externo</b> e
              acrescente o e-mail do canal em <b>Usuários de teste</b>
              (ou <b>Público-alvo → Usuários de teste</b>) — sem isso o login
              é recusado.</li>
          <li>Em <b>Credenciais → Criar credenciais → ID do cliente OAuth</b>,
              escolha o tipo <b>App para computador</b>. Conta de serviço não
              funciona para upload.</li>
          <li>Baixe o JSON, renomeie para <code>client_secret.json</code> e
              coloque em:<br><code>${e.pasta}</code></li>
          <li>Volte aqui e clique em <b>Testar a conexão</b>. O navegador
              pede a autorização e o painel mostra o nome do canal — assim você
              confere que deu certo antes de gastar um upload.</li>
        </ol>
        <p class="dica"><b>Atenção antes de investir nisso:</b> projeto de API
          que não passou pela auditoria de conformidade do Google sobe o vídeo
          travado como <b>privado</b>, mesmo pedindo outra coisa. Nesse caso o
          upload economiza mandar o arquivo e colar os textos, mas a publicação
          final continua no Studio.</p>
      </details>`;
    mostrar("ytPronto", false);
    return;
  }

  $("ytEstado").innerHTML = (e.conectado
    ? `<div class="achado">Conta conectada. O vídeo sobe com miniatura,
       legenda e vai para a playlist da série.</div>`
    : `<div class="aviso">Credencial encontrada. Na primeira vez o navegador
       vai abrir para você autorizar a conta do canal.</div>`) +
    `<p class="dica" style="margin-top:8px">
       <button class="acao leve" id="btTestarYT">Testar a conexão</button>
       <span style="margin-left:10px">confere a credencial e mostra o canal —
       não publica nada</span></p>
     <div id="ytTeste"></div>`;
  mostrar("ytPronto", true);

  $("btSubir").onclick = subirParaYoutube;
  $("btTestarYT").onclick = testarYoutube;
}

async function subirParaYoutube() {
  if (!TAREFA || !TAREFA.arquivo) return;

  $("btSubir").disabled = true;
  mostrar("ytAndamento", true);
  $("ytResultado").innerHTML = "";

  let r;
  try {
    r = await pedir("/api/youtube/subir", {
      pasta: TAREFA.pasta,
      arquivo: TAREFA.arquivo,
      titulo: TAREFA.titulo,
      playlist: TAREFA.playlist || "",
      privacidade: $("ytPrivacidade").value,
    });
  } catch (erro) {
    mostrar("ytAndamento", false);
    $("btSubir").disabled = false;
    return aviso("ytResultado", erro.message, "erro");
  }

  const relogio = setInterval(async () => {
    const t = await pedir(`/api/tarefa/${r.tarefa}`);
    $("ytBarra").style.width = (t.progresso * 100) + "%";
    $("ytEtapa").textContent = t.etapa || "";
    $("ytDetalhe").textContent = t.detalhe || "";
    $("ytRegistro").innerHTML = (t.log || []).slice(-10).join("<br>");

    if (t.estado === "pronto") {
      clearInterval(relogio);
      mostrar("ytAndamento", false);
      const v = t.resultado;
      $("ytResultado").innerHTML = `
        <div class="publicado">
          No ar como <b>${v.privacidade}</b>:<br>
          <a href="${v.url}" target="_blank" rel="noopener">${v.url}</a>
          ${v.avisos.length ? "<br><br>" + v.avisos.map(a => "• " + a).join("<br>") : ""}
          <div style="margin-top:12px">
            <button class="acao leve" id="btApagarLocal">Apagar o vídeo deste Mac</button>
            <span class="dica" style="margin-left:8px">só os MP4; capa, legenda e ficha ficam</span>
          </div>
        </div>`;
      $("btApagarLocal").onclick = async () => {
        const b = $("btApagarLocal");
        if (b.dataset.confirma !== "1") {       // dois cliques: o primeiro só pergunta
          b.dataset.confirma = "1"; b.textContent = "Confirmar: apagar o vídeo e os Shorts"; return;
        }
        b.disabled = true;
        try {
          const r = await pedir("/api/apagar-videos", { pasta: TAREFA.pasta });
          b.textContent = `Apagado (${r.mb} MB liberados)`;
        } catch (e) { b.disabled = false; aviso("ytResultado", e.message, "erro"); }
      };
    }
    if (t.estado === "erro") {
      clearInterval(relogio);
      mostrar("ytAndamento", false);
      $("btSubir").disabled = false;
      aviso("ytResultado", t.erro, "erro");
    }
  }, 900);
}


/* ==========================================================================
   Shorts — você marca os trechos, o Estúdio reenquadra e legenda.
   ========================================================================== */
function addTrecho(inicio = "", fim = "") {
  const linha = document.createElement("div");
  linha.className = "trecho";
  linha.innerHTML = `
    <div><label>Começa em</label>
      <input type="text" class="s-ini" placeholder="hh:mm:ss" value="${inicio}"></div>
    <div><label>Termina em</label>
      <input type="text" class="s-fim" placeholder="hh:mm:ss" value="${fim}"></div>
    <button class="acao leve s-ouvir" type="button">Ouvir</button>
    <button class="tirar" type="button" title="Tirar este trecho">×</button>`;

  linha.querySelector(".tirar").onclick = () => linha.remove();
  linha.querySelector(".s-ouvir").onclick = () => {
    $("inicio").dataset.guardado = $("inicio").value;
    $("inicio").value = linha.querySelector(".s-ini").value;
    conferir().finally(() => {
      $("inicio").value = $("inicio").dataset.guardado;
      $("cartaoCorte").scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };
  $("trechos").appendChild(linha);
}

async function gerarShorts() {
  const trechos = [...$("trechos").querySelectorAll(".trecho")]
    .map(l => ({ inicio: l.querySelector(".s-ini").value.trim(),
                 fim: l.querySelector(".s-fim").value.trim() }))
    .filter(t => t.inicio && t.fim);

  if (!trechos.length)
    return aviso("shortsResultado", "Marque pelo menos um trecho.", "erro");

  aviso("shortsResultado", "");
  $("btShorts").disabled = true;
  mostrar("shortsAndamento", true);

  const d = dadosDaArte();
  const r = await pedir("/api/shorts", {
    url: $("url").value.trim(),
    video_id: VIDEO.id,
    pasta: (TAREFA && TAREFA.pasta) || "",
    data: $("data").value,
    formato: FORMATO,
    serie: d.serie, episodio: d.ep, tema: d.tema, referencia: d.ref,
    visual: { ...VISUAL, vars: d.vars },
    trechos,
    modo: $("modoShort").value,
    legendar: $("legendarShort").value === "sim",
    tarja: $("tarjaShort").value,
  });
  $("btPararShorts").disabled = false; $("btPararShorts").textContent = "Parar";
  $("btPararShorts").onclick = () => pararTarefa(r.tarefa, $("btPararShorts"));

  const relogio = setInterval(async () => {
    const t = await pedir(`/api/tarefa/${r.tarefa}`);
    $("shortsBarra").style.width = (t.progresso * 100) + "%";
    $("shortsEtapa").textContent = t.etapa || "";
    $("shortsDetalhe").textContent = t.detalhe || "";
    $("shortsRegistro").innerHTML = (t.log || []).slice(-10).join("<br>");

    if (t.estado === "pronto") {
      clearInterval(relogio);
      mostrar("shortsAndamento", false);
      $("btShorts").disabled = false;
      if (!TAREFA || !TAREFA.pasta) TAREFA = { ...(TAREFA || {}), pasta: t.pasta_shorts };
      mostrarShorts(t.shorts, t.pasta_shorts);
    }
    if (t.estado === "erro") {
      clearInterval(relogio);
      mostrar("shortsAndamento", false);
      $("btShorts").disabled = false;
      aviso("shortsResultado", t.erro, "erro");
    }
  }, 900);
}


/* Transcreve a transmissão aqui na máquina, quando o YouTube ainda não tem. */
async function transcreverLocal() {
  const b = $("btTranscrever");
  b.disabled = true;
  b.textContent = "Transcrevendo…";

  let r;
  try {
    r = await pedir("/api/transcrever-local", {
      url: $("url").value.trim(),
      video_id: VIDEO.id,
      duracao: VIDEO.duracao,
      formato: FORMATO,
    });
  } catch (e) {
    b.disabled = false;
    b.textContent = "Transcrever aqui na máquina";
    return aviso("avisoAnalise", e.message, "erro");
  }

  const relogio = setInterval(async () => {
    const t = await pedir(`/api/tarefa/${r.tarefa}`);
    b.textContent = `${t.etapa} ${t.detalhe || ""}`;

    if (t.estado === "pronto") {
      clearInterval(relogio);
      const v = t.resultado;
      $("inicio").value = v.inicio_texto;
      $("fim").value = v.fim_texto;
      $("btConferir").disabled = false;
      $("resumoVideo").innerHTML =
        `<b>${VIDEO.titulo}</b><br>Transmissão de ${hms(VIDEO.duracao)} · ` +
        `${v.blocos} trechos transcritos aqui na máquina.`;
      aviso("achado", v.achou
        ? `Achei o começo em <b>${v.inicio_texto}</b> — reconheci
           “${v.motivo}”.<q>“…${v.trecho}…”</q>
           Confira com <b>Ouvir o trecho</b> antes de produzir.`
        : `Transcrevi, mas não achei uma frase clara de abertura da Palavra.
           Use <b>Ouvir o trecho</b> para se localizar e ajuste na mão.`,
        v.achou ? "achado" : "aviso");
      $("alternativas").innerHTML = (v.alternativas || [])
        .map(a => `<button data-t="${a.segundos}">${a.texto} · ${a.motivo}</button>`)
        .join("");
    }
    if (t.estado === "erro") {
      clearInterval(relogio);
      b.disabled = false;
      b.textContent = "Transcrever aqui na máquina";
      aviso("avisoAnalise", t.erro, "erro");
    }
  }, 1500);
}


/* Lê a transcrição e propõe trechos. Não é detecção de viralidade: procura as
   marcas de um bom recorte de pregação (começa em frase, fala com a igreja,
   tem uma virada) e deixa a escolha com você. */
async function sugerirTrechos() {
  const b = $("btSugerir");
  b.disabled = true;
  b.textContent = "Lendo a pregação…";
  try {
    const r = await pedir("/api/sugerir-trechos", {
      video_id: VIDEO.id,
      inicio: $("inicio").value,
      fim: $("fim").value,
    });

    if (!r.trechos.length) {
      aviso("sugestoes", "Não achei trechos que se sustentem sozinhos. " +
                         "Marque na mão usando a transcrição.", "aviso");
    } else {
      $("sugestoes").innerHTML =
        `<p class="dica" style="margin-top:14px">Leia e escolha. Clicar em
          <b>Usar</b> acrescenta o trecho à lista acima.</p>` +
        r.trechos.map((t, i) => `
          <div class="sugestao">
            <header>
              <b>${t.inicio_texto} → ${t.fim_texto}</b>
              <span class="dur">${t.segundos}s</span>
              <button data-i="${i}">Usar</button>
            </header>
            <p>“${t.texto}”</p>
          </div>`).join("");

      $("sugestoes").onclick = e => {
        const bt = e.target.closest("button[data-i]");
        if (!bt) return;
        const t = r.trechos[bt.dataset.i];
        addTrecho(t.inicio_texto, t.fim_texto);
        bt.disabled = true;
        bt.textContent = "Na lista";
      };
    }
  } catch (e) {
    aviso("sugestoes", e.message, "erro");
  } finally {
    b.disabled = false;
    b.textContent = "Sugerir trechos";
  }
}


/* Mostra os Shorts de uma produção, com o caminho e os botões de abrir. */
function mostrarShorts(lista, pasta) {
  if (!lista || !lista.length) {
    $("shortsResultado").innerHTML = "";
    return;
  }
  $("shortsResultado").innerHTML = `
    <div class="prontos">
      ${lista.map(s => `<div>
         <b>${esc(s.nome || s.arquivo.split("/").pop())}</b>
         <span>${s.segundos}s · ${s.mb} MB
           <button class="abrir" data-c="${esc(s.arquivo)}" data-r="1">abrir</button>
         </span>
       </div>`).join("")}
    </div>
    <div class="onde">
      <span>Os Shorts estão em</span>
      <code>${esc(pasta)}</code>
      <button class="acao" data-c="${esc(pasta)}">Abrir a pasta dos Shorts</button>
    </div>`;

  $("shortsResultado").onclick = ev => {
    const b = ev.target.closest("button[data-c]");
    if (b) pedir("/api/abrir-pasta",
                 { caminho: b.dataset.c, revelar: b.dataset.r === "1" });
  };
}

/* ==========================================================================
   Biblioteca — voltar a um vídeo já produzido, para gerar Shorts dele depois.
   ========================================================================== */
async function montarBiblioteca() {
  const alvo = $("biblioteca");
  alvo.innerHTML = `<p class="dica">Procurando…</p>`;

  const { producoes } = await pedir("/api/producoes");
  if (!producoes.length) {
    alvo.innerHTML = `<p class="dica">Nenhum vídeo produzido ainda.</p>`;
    return;
  }

  alvo.innerHTML = producoes.map((p, i) => {
    const nome = [p.serie, p.episodio].filter(Boolean).join(" ");
    const selos = [
      p.tem_shorts ? `<span class="selo">tem Shorts</span>` : "",
      p.url ? "" : `<span class="selo falta">falta o link</span>`,
    ].join("");
    return `
      <div class="producao">
        <div class="quem">
          <b>${nome || p.pasta.split("/").pop()}</b>
          <span>${[p.data, p.tema, p.mb + " MB"].filter(Boolean).join(" · ")}</span>
        </div>
        <div class="selos">${selos}</div>
        <button data-i="${i}">Abrir</button>
        <button class="apagar-prod" data-apagar="${i}" title="Apagar esta produção" aria-label="Apagar">×</button>
      </div>`;
  }).join("");

  alvo.onclick = async e => {
    const x = e.target.closest("button[data-apagar]");
    if (x) {
      // dois toques: o primeiro pergunta, o segundo apaga a pasta inteira
      const card = x.closest(".producao");
      if (!card.classList.contains("confirmando")) {
        alvo.querySelectorAll(".producao.confirmando").forEach(c => {
          c.classList.remove("confirmando"); c.querySelector(".pergunta")?.remove();
        });
        card.classList.add("confirmando");
        card.querySelector(".selos").insertAdjacentHTML("beforeend",
          `<span class="pergunta">Apagar o vídeo e os Shorts do disco? Toque no × de novo.</span>`);
        return;
      }
      x.disabled = true;
      try {
        await pedir("/api/apagar-producao", { pasta: producoes[x.dataset.apagar].pasta });
        if (ESTUDO) { await carregarEstudos(); ESTUDO = ESTUDOS.find(s => s.id === ESTUDO.id) || ESTUDO; mostrarEstudoAtual(); }
        montarBiblioteca();
      } catch (err) { alert(err.message); x.disabled = false; }
      return;
    }
    const b = e.target.closest("button[data-i]");
    if (b) abrirProducao(producoes[b.dataset.i], b);
  };
}

async function abrirProducao(p, botao) {
  let url = p.url;
  if (!url) {
    url = prompt(
      "Esta pasta é antiga e não guarda o link da transmissão.\n" +
      "Cole o link do YouTube — eu gravo e não pergunto de novo.");
    if (!url) return;
  }

  botao.disabled = true;
  botao.textContent = "Abrindo…";
  try {
    const r = await pedir("/api/abrir-producao", { pasta: p.pasta, url });
    const d = r.producao;

    VIDEO = { id: r.video_id, titulo: d.titulo || "", duracao: 0 };
    TAREFA = { pasta: d.pasta || p.pasta, arquivo: d.arquivo || p.arquivo,
               titulo: d.titulo || "", playlist: d.playlist || "" };

    $("url").value = d.url || url;
    if (d.inicio) $("inicio").value = d.inicio;
    if (d.fim) $("fim").value = d.fim;
    if (d.serie) $("serie").value = d.serie;
    if (d.episodio) $("episodio").value = d.episodio;
    if (d.tema) $("tema").value = d.tema;
    if (d.referencia) $("referencia").value = d.referencia;
    if (d.visual && d.visual.cor) { VISUAL = { ...d.visual }; escreverVisual(); }

    $("resumoVideo").innerHTML =
      `<b>${d.titulo || (d.serie + " " + d.episodio)}</b><br>` +
      `Vídeo já produzido, retomado da biblioteca · ${r.blocos} trechos de ` +
      `transcrição carregados.`;
    aviso("achado", "", "achado");
    // retomar da biblioteca vale como analisar: os campos ficam editáveis e a
    // produção liberada, caso você queira refazer o corte ou trocar o tema
    travarOQueDependeDoVideo(false);
    $("btConferir").disabled = false;

    mostrar("cartaoShorts", true);
    if (!$("trechos").children.length) addTrecho();
    $("sugestoes").innerHTML = "";
    mostrarShorts(r.shorts, r.pasta_shorts);
    mostrarFonte(r.fonte);
    $("cartaoShorts").scrollIntoView({ behavior: "smooth", block: "start" });
    atualizarPrevia();
  } catch (e) {
    aviso("avisoAnalise", e.message, "erro");
  } finally {
    botao.disabled = false;
    botao.textContent = "Abrir";
  }
}


/* Deixa à vista de qual arquivo os Shorts vão ser recortados. */
function mostrarFonte(f) {
  const el = $("fonteShorts");
  if (!el) return;
  if (f && f.tem) {
    el.innerHTML = `Recortando de <code>${esc(f.arquivo)}</code> — ` +
                   `a transmissão baixada, ${f.mb} MB.`;
  } else {
    el.innerHTML = `A transmissão não está mais no disco. Ao gerar o primeiro ` +
                   `Short ela será baixada de novo (leva alguns minutos).`;
  }
}


/* Confere a credencial sem publicar nada: pergunta ao YouTube qual é o canal. */
async function testarYoutube() {
  const b = $("btTestarYT");
  b.disabled = true;
  b.textContent = "Testando…";
  try {
    const r = await pedir("/api/youtube/testar", {});
    const tem = r.playlists.length;
    aviso("ytTeste",
      `Conectado ao canal <b>${esc(r.canal)}</b>, com ${tem} playlists.` +
      (tem ? `<br><span class="dica">${r.playlists.slice(0, 8)
              .map(esc).join(" · ")}${tem > 8 ? " …" : ""}</span>` : ""),
      "achado");
  } catch (e) {
    aviso("ytTeste", e.message, "erro");
  } finally {
    b.disabled = false;
    b.textContent = "Testar a conexão";
  }
}
