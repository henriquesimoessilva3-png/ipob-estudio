# Fila do Estúdio IPOB

Os três itens que estavam aqui — legendas, upload e Shorts — foram feitos.
O que sobrou está abaixo.

---

## Esperando você

### A credencial do YouTube

O upload está pronto e testado até onde dá sem tocar no canal. Falta uma coisa
que só você pode fazer: criar a credencial OAuth na sua conta Google. O painel
mostra o passo a passo no cartão "Subir para o YouTube", quando você termina um
vídeo. São cinco minutos, uma vez só.

**Decida antes de fazer:** projeto de API que não passou pela auditoria de
conformidade do Google sobe o vídeo travado como *privado*, mesmo pedindo outra
coisa. Se for esse o caso, o upload poupa mandar o arquivo e colar os textos,
mas a publicação final continua no Studio. Vale conferir se ainda é assim antes
de investir na auditoria.

O painel tem um botão **Testar a conexão** que valida a credencial sem publicar
nada — ele só pergunta ao YouTube qual canal a conta controla e lista as
playlists. Use isso primeiro: se o canal que aparecer for o da igreja, o resto
funciona.

O que **não** foi testado, e só será quando você conectar: o upload de verdade,
a miniatura, a legenda e a entrada na playlist. O código está escrito e as
mensagens de erro estão mapeadas (cota, conta sem canal, permissão, autorização
expirada), mas nenhum vídeo foi enviado ao canal.

---

## Feito em 16/09/2026, conferir no próximo Short

O recorte dos Shorts deixou de ser fixo. Agora é medido em cada trecho:
amostram-se 20 quadros, acha-se onde está a câmera (por nitidez) e por onde o
pregador andou (por variação no tempo), e o corte é a área que contém todo o
movimento dele.

**O que isso resolveu:** o recorte fixo tinha sido medido num culto com tela
dividida. Numa transmissão em câmera cheia ele recortava a região errada e o
pregador saía de quadro — foi o que aconteceu nos Shorts do APOCALIPSE.

**O achado do caminho:** a mesa de transmissão alterna entre câmera cheia e um
quadro com a câmera num painel menor ao lado do versículo projetado, e essa
troca acontece no meio da pregação. Quando ela cai DENTRO do trecho escolhido,
nenhum recorte serve — o que enquadra num layout decapita no outro. Nesse caso
o Estúdio detecta a instabilidade e usa o quadro inteiro, que é sempre seguro.

**A borda do "pregador cheio" já foi corrigida:** `enquadrar()` devolve o
centro do movimento e o corte 9:16 se ancora nele (revisão de 01/10/2026
confirmou no código). Falta só ver num Short real que o rosto não encosta
mais na borda.

Falta conferir no uso: se a tolerância de instabilidade (`VARIACAO_MAXIMA` em
`nucleo/enquadrar.py`, hoje 0.06) está no ponto. Muito baixa, ele desiste de
recortar à toa; muito alta, volta a cortar o pregador.

## Revisão de 01/10/2026

Corrigido e testado com dados de teste (não com uma transmissão real):

- **Aprendizado separado por formato.** EBD e culto agora têm cada um a sua
  mediana (`centro_aprendido` e `sobra_aprendida` dentro de cada formato na
  config). Reeditar o mesmo vídeo substitui a medida em vez de somar. As 5
  medidas antigas não sabem de qual formato são: elas valem enquanto cada
  formato não tiver 2 medidas próprias, e depois saem da conta.
- **Transcrição do Whisper gravada** em `trabalho/<id>/transcricao-local.json`.
  Sobrevive a reiniciar o painel.
- **Config relida na hora de gravar** a produção — o que você salvar no painel
  durante a renderização não se perde mais.
- **Travas atômicas** e trava também no envio ao YouTube: clique duplo não
  publica duas vezes. O link publicado fica na ficha da produção.
- **Só `video.mp4` vale como download pronto** — o pedaço mudo de um download
  interrompido não é mais reaproveitado.
- **Taxa de quadros igual na capa e na pregação.** A capa entrava a 25 fps; o
  vídeo saía com taxa variável. No ffmpeg 4 o concat chegava a travar.

Avaliado e **não** feito: baixar só o trecho da pregação
(`--download-sections`). O corte sem reencodar começa no quadro-chave anterior,
o que deslocaria o início em alguns segundos — e o começo exato do convite é o
que mais importa aqui. O ganho seria um ou dois minutos de download.

Backup do código antes da revisão: `.backup-2026-10-01-revisao/` na raiz do
projeto. Pode apagar depois de conferir um domingo.

## Layouts de capa (01/10/2026)

A capa ganhou composições além da clássica: no culto, **Foto cheia**,
**Painel**, **Moldura** e **Tema grande**; na EBD, **Quadro** e **Noturno**.
Todas usam as mesmas duas cores da série e a foto em duotone, e foram
conferidas renderizadas com série longa ("A Confissão de Fé de Westminster"),
tema de duas linhas e dois pregadores. O layout fica gravado com a série.

Conferido no Chromium de fora, não no Chrome do Mac: na primeira capa real
vale olhar o PNG — a fonte dos títulos é a Helvetica do sistema, que lá não
existia (saiu em Open Sans/Arial).

**Mais três, claros, depois da pesquisa no YouTube** (IP Pinheiros, IP Semear,
IP Catanduva — o Henrique aprovou a linha "branco com verde"): **Branco e
verde**, **Cartão** e **Recorte**, para culto e EBD. Usam o pregador
**recortado sem fundo** (`assets/pregadores/*-recorte.png`, feitos com rembg a
partir das fotos de 400 px; o microfone fica, é parte da cena). Para trocar a
foto de um pregador: salve um PNG sem fundo e aponte em
`config.json → pregadores → recorte`. Fotos melhores (posadas, em boa luz)
melhorariam muito esses três layouts — os quadros de vídeo são o limite hoje.

**Segunda leva clara (14 layouts, 01/10/2026):** Faixa lateral, Dividido,
Rodapé, Citação, Cartaz, Editorial, Bloco, Foto clara, Tinta suave, Duas cores,
Número, Moldura clara, Coluna e Etiqueta — todos para culto e EBD, seção 11 do
CSS. Com isso o culto tem 22 opções e a EBD 20. Conferidos com tema curto e
longo. Se algum nunca for usado, basta apagar a entrada em `config.json →
layouts` que ele some da galeria (o código pode ficar).

Ideias que ficaram para depois:
- Uma **foto do culto** como fundo (um quadro da própria transmissão) em vez
  dos fundos genéricos — o duotone já uniformiza qualquer foto.
- Tarjas combinando com cada layout (hoje a tarja é a mesma para todos).
- Capa dos Shorts (9:16) com o mesmo sistema de layouts.

## Estudos (01/10/2026)

O cartão Aparência agora começa por **Estudo existente / Novo estudo**. Um
estudo guarda série, playlist, pregador, visual (layout + cores) e a lista dos
episódios produzidos; só pode haver um em andamento por formato. Cada
produção acrescenta o episódio à linha do tempo (reeditar o mesmo número
substitui) e o painel passa a propor o número seguinte. Fica em
`config.json → estudos`; rotas `/api/estudos` no `painel.py`. O mecanismo
antigo (`series_salvas`, digitar o nome da série) continua valendo no modo
"Novo estudo", para não perder nada.

## Anotado, sem pressa

### O aprendizado precisa de mais domingos

O palpite do corte usa a mediana dos seus últimos cortes. Hoje tem **dois**
registros (os que você conferiu em 29/08/2026). Com uns seis o número fica
firme. Não precisa fazer nada — cada vídeo produzido registra sozinho.

Se algum domingo atípico entortar o palpite, dá para apagar a medida errada em
`dados/config.json`, em `aprendizado.cortes`.

### O ícone da EBD

O projeto do Filmora de 12/11/2023 usava um `icone EBD.jpg` — a faixa verde
vertical com "ESCOLA BÍBLICA DOMINICAL". Não foi recriado: a capa da EBD hoje
segue o visual do Westminster, que é o mais recente. Só volta se você quiser
aquele layout antigo.

### Limpeza do `trabalho/`

Os downloads ficam guardados para reaproveitar quando você reedita o mesmo
culto. Se encher o disco, apagar a pasta é seguro — o Estúdio baixa de novo se
precisar.

### Shorts: um player para marcar seria mais confortável

A sugestão automática de trechos já existe (botão **Sugerir trechos**), lendo a
transcrição. O que falta é conforto: para ajustar um trecho na mão você digita
os tempos. Um player com a onda do áudio seria melhor — mas é conforto, não
capacidade.

A escolha final continua sua, e deve continuar: as ferramentas de "detecção de
viralidade" usam modelo treinado em inglês e erram feio em português.
