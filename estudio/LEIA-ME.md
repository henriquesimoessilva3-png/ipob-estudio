# Estúdio IPOB

Painel local para transformar a transmissão do domingo no vídeo editado da
pregação — corte, capa, tarja, título e descrição — sem abrir o Filmora.

## Como abrir

Clique duas vezes em **Abrir Estúdio IPOB.command**. O navegador abre sozinho
em `http://localhost:4747`. Para fechar, feche a janela do Terminal.

Pelo terminal, se preferir:

```bash
cd "estudio" && python3 painel.py
```

## Como usar, semana a semana

1. **Cole o link** da transmissão e clique em *Analisar transmissão*.
   O Estúdio baixa a transcrição automática do YouTube e procura a frase em que
   o pastor abre a Palavra. Ele mostra o trecho que encontrou.
2. **Confira o corte.** O botão *Ouvir o trecho* mostra o que é falado naquele
   ponto. Se o palpite errou, use as alternativas ou digite o tempo.
3. **Preencha** série, episódio, tema, referência e quem pregou.
3b. **Grave o corte.** Conferiu "Começa em" e "Termina em"? Clique em
   **Gravar corte**. Ele fica guardado para esta transmissão (analisar de novo
   devolve o seu corte, não um palpite) e já entra no aprendizado. Produzir
   também grava, então o botão é para quando você quer marcar e continuar
   depois.

4. **Escolha o estudo.** No cartão Aparência há dois botões:
   - **Estudo existente** — a lista das séries em andamento (e as encerradas).
     Clique na sua e pronto: a capa vem igual à das semanas anteriores e o
     número do episódio já é o seguinte. A linha do tempo mostra o que já foi
     produzido. Quando a série acabar, **Encerrar estudo**.
   - **Novo estudo** — dê o nome da série, escolha o **layout da capa** (as
     miniaturas mostram a sua capa de verdade) e as **cores**, e clique em
     **Iniciar estudo com esta aparência**. A partir daí ele aparece em
     "Estudo existente". Culto e EBD têm estudos separados.
   Precisa mudar algo no meio da série? **Ajustar aparência** abre layouts e
   cores; o que você produzir fica gravado como o novo visual do estudo.
5. **Produzir.** Sai uma pasta em `PROJETO - EDICAO DE VIDEOS/Vídeos Editados/<Culto Noturno ou EBD>/<estudo>/<nº - data - tema>/` com:
   - o MP4 pronto
   - `capa.jpg` (a miniatura do YouTube)
   - `titulo e descricao.txt` (com o recado do WhatsApp junto)
   - `legenda.srt` (para subir em "Legendas" no Studio)

6. **Subir** — ou pelo botão do painel (veja abaixo), ou no Studio na mão,
   colando título e descrição e escolhendo a miniatura.
7. **Shorts**, se quiser: marque 2 ou 3 trechos e o Estúdio reenquadra em 9:16,
   põe a tarja e queima a fala na tela.

## Onde ficam os arquivos

| Pasta | O que é |
|---|---|
| `PROJETO - EDICAO DE VIDEOS/Vídeos Editados/` | os vídeos prontos: formato → estudo → episódio (vídeo e Shorts juntos). Fica no Google Drive, então sobe para a nuvem |
| `~/Movies/Estudio IPOB/saida/` | produções antigas, antes desta organização — a biblioteca ainda as lê |
| `~/Movies/Estudio IPOB/trabalho/` | downloads e transcrições, para reaproveitar |

**Ficam fora do Google Drive de propósito.** Uma transmissão de 1h40 em 1080p
passa de 1 GB; se ficasse na pasta do projeto, subiria para a nuvem toda semana.
A pasta `trabalho` pode ser apagada quando quiser — só faz o Estúdio baixar de
novo se você reeditar o mesmo culto.

## Mudar o visual

O painel resolve cor, fundo, altura da tarja e o logo do canto. Para ir além:

- **`artes/estilo.css`** — todos os tamanhos, posições e cores. As variáveis do
  topo do arquivo são o que você mais vai querer mexer. Salve e atualize a
  página: a prévia usa exatamente esse arquivo.
- **`dados/config.json`** — pregadores, séries, modelos de cor e os padrões
  (duração da capa, sobra no final, bitrate).
- **`assets/fundos/`** — as imagens de fundo da capa. Jogue um `.jpg` aí e ele
  aparece na lista. Qualquer foto serve: ela é tingida na cor da série.
- **`assets/pregadores/`** — as fotos. Para trocar, substitua o arquivo mantendo
  o nome, ou acrescente um pregador novo em `config.json`.

## Como o corte é encontrado

Não há adivinhação: o culto sempre segue a mesma ordem, e o que muda é o minuto.

**O começo** é o aviso de que as crianças descem para as classes — a pregação
vem logo em seguida. Esse marcador manda em todos os outros: uma frase como
"abram comigo as escrituras" pode ser uma referência cruzada no meio da
pregação, mas as crianças só descem uma vez. Se o aviso não aparecer, o
Estúdio cai nas frases de abertura da Palavra (`busca_do_corte.gatilhos_inicio`
no `config.json` — pode acrescentar as suas) e na posição típica.

**O fim** é o "amém" da oração final: a pregação sempre fecha com oração, e
logo depois já dá para cortar. Procura-se o último amém do trecho final.

**E ele aprende.** Cada vídeo que você produz vira uma medida: em que fração da
transmissão a pregação começou e quantos segundos sobraram no fim. O palpite da
semana seguinte usa a mediana dos últimos 12 cortes seus — um domingo atípico
não estraga o próximo. Fica em `config.json`, em `aprendizado`.

## Legendas

Sai um `legenda.srt` junto com o vídeo, feito a partir da transcrição, já com
os tempos ajustados ao corte e à capa. É só subir em "Legendas" no Studio.

Se a transmissão ainda não tiver transcrição automática, o painel oferece
**transcrever aqui na máquina** (Whisper). Baixa só o áudio e roda local — na
primeira vez o modelo é baixado, uns 500 MB, uma vez só.

## Subir para o YouTube

O painel sobe o vídeo, aplica a miniatura, manda a legenda e joga na playlist
da série. Nada sobe sozinho: só quando você clica.

Precisa de uma credencial OAuth criada por você uma única vez — o painel mostra
o passo a passo quando você chega nessa parte. **Antes de investir nisso:**
projeto de API que não passou pela auditoria de conformidade do Google sobe o
vídeo travado como privado, mesmo pedindo outra coisa. Nesse caso o upload
poupa mandar o arquivo e colar os textos, mas a publicação final continua no
Studio.

## Voltar a um vídeo de outra semana

No passo 1 tem **Ou retome um vídeo já produzido**. Ali estão todas as
produções: escolha uma e o painel recarrega os tempos de corte, a série, o
tema e as cores, e carrega a transcrição do disco — sem rede, sem refazer nada.
Serve principalmente para gerar Shorts de uma pregação antiga.

Cada produção grava um `producao.json` na própria pasta com o link e os tempos.
Pastas feitas antes disso existir aparecem marcadas com **falta o link**: o
painel pede uma vez, grava, e não pergunta de novo.

Ao retomar, os campos de corte ficam editáveis e a produção liberada — dá para
refazer o vídeo com outro tema sem começar do zero. E se a produção já tiver
Shorts, eles aparecem listados no passo 6, com o caminho e o botão para abrir
a pasta.

## Som

A transmissão chega por volta de **-34 LUFS** e o YouTube trabalha em **-14**.
Como ele só abaixa o que está alto e nunca levanta o que está baixo, publicar
sem corrigir faz o vídeo tocar baixo demais — é o que vinha acontecendo com o
canal. O Estúdio mede o som do trecho antes de renderizar e corrige com ganho
constante (duas passadas, para não bombear o volume nas pausas). Custa uns 2
segundos a mais. Vale para o vídeo e para os Shorts — no celular, na rua, som
baixo é ainda pior. Desliga em `padroes.normalizar_audio`.

## Shorts

Você marca os trechos — ou clica em **Sugerir trechos** e escolhe de uma lista
curta.

A sugestão **não é detecção de viralidade**: as ferramentas que prometem isso
usam modelo treinado em inglês e escolhem mal em português. O que o Estúdio faz
é varrer a transcrição procurando as marcas de um bom recorte de pregação —
começa em início de frase, fala com a igreja em vez de só ler o texto, tem uma
virada ("mas", "portanto"), termina a ideia — e evita os primeiros e últimos
minutos, que são introdução e oração. Sai uma lista para você ler, não uma
decisão tomada. Os pesos estão em `nucleo/trechos.py`.

Dois enquadramentos:

- **Completo** — o quadro inteiro no meio, com uma cópia borrada dele no fundo.
  Não perde nada da cena.
- **Perto** — recorta o centro e amplia. O pregador fica grande, mas perde-se
  as laterais.

A fala é queimada na tela, porque Short se assiste sem som. Quando terminam, o
painel mostra o caminho completo da pasta e um botão para abri-la no Finder —
e cada Short tem um **abrir** que o revela no Finder.

## Quando algo não funciona

**"Não é possível acessar esse site" / ERR_CONNECTION_REFUSED em localhost:4747**
— o painel não está no ar. Ele roda enquanto a janela do Terminal estiver
aberta e **não sobrevive a reiniciar o Mac**. Clique duas vezes em
**Abrir Estúdio IPOB.command** e pronto. Pode clicar quantas vezes quiser: se
já estiver rodando, ele só abre o navegador.

Nada se perde quando o painel cai — série, cores, episódio e o que ele aprendeu
com os seus cortes ficam em `dados/config.json`, e os vídeos em
`~/Movies/Estudio IPOB/`. O que fica no log é só o histórico de execução,
em `~/Movies/Estudio IPOB/painel.log`.


**"Essa transmissão não tem transcrição automática"** — o YouTube leva algumas
horas depois da live para gerar. Não trava nada: digite o minuto de início.

**"O YouTube pediu confirmação de que não é robô"** — abra o Chrome e entre na
sua conta do YouTube. O Estúdio usa os cookies do Chrome; nada sai da máquina.

**"O YouTube bloqueou os formatos de vídeo"** — o yt-dlp envelheceu. No terminal:

```bash
pip3 install -U yt-dlp yt-dlp-ejs
```

O YouTube passou a exigir um motor JavaScript para liberar os formatos. O
Estúdio usa o Deno, o Node ou o Bun, o que estiver instalado — aqui está usando
o Node.

## O que o Estúdio precisa

ffmpeg · yt-dlp · Google Chrome (usado invisível, para desenhar as artes e as
legendas dos Shorts) · um motor JavaScript para o yt-dlp · Python 3 com Flask,
Pillow, Playwright, faster-whisper e as bibliotecas do Google. O painel mostra
no alto se está tudo no lugar.

Nota sobre o ffmpeg desta máquina: ele foi compilado sem libass e sem
freetype, então os filtros `subtitles` e `drawtext` não existem aqui. Por isso
a legenda dos Shorts é desenhada como imagem pelo Chrome e sobreposta — o que
saiu melhor de qualquer forma, porque usa a mesma tipografia do resto.

## O que ainda não faz

- **Não sobe no YouTube.** Entrega o pacote pronto e você publica no Studio.
- **Não faz cortes verticais** para Shorts.

Os três estão na fila, com o levantamento já feito de cada um — o que falta, o
que já está pronto no código e as armadilhas conhecidas: ver **FILA.md**.
