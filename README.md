# Infomed

<img src="https://gestlreythduxcbqprab.supabase.co/storage/v1/object/public/logos/120afd64-6911-4e54-81ab-1e656e3c5037-1789168844649.jfif"  width="300">

O Infomed é uma plataforma de gestão de estoque e triagem de compatibilidade. Podendo ser usado por 1 pessoa ou 1 cuidador que gerencia os medicamentos de seus pacientes.

![fluxograma](data/images/Fluxograma.png)

# Backend com python

No Python, temos alguns motores;

## app.py
Aqui funciona como uma escuta, traz as informações do bubble e quando processado leva de volta quando os dados são processados, para o bubble e para o n8n

## ai_handler.py
[ai_handler.py](core/ia/ai_handler.py) basicamente é o arquivo de chamada/comunicação com as ias do [google](https://aistudio.google.com) e do [groq](https://console.groq.com) (configure suas apis em .env.example) se uma não retornar ou falhar no meio do caminho, a outra continua de onde parou. Servindo principalmente para receber e devolver prompts, se ja tiver configurado seu .env, pode utilizar o teste_ai.py para ver se retornam.

## complementos.py
[complementos.py](core/complementos.py) ele busca os dados no [db](data/solidificados.json) e se tiver dados fatando, ele complementa os dados de capos imcompatibilidades e efeitos colaterais que veio da requisição do remedio x usando prompt de contexto e os de busca, veja em prompt_farmaceutico; montado para encaixotar o que veio da UI o maximo possivel para entregar o melhor resultado no match.

## incompativeis.py
[incompativeis.py](core/incompativeis.py) aqui se inicia a checagem de incompatibilidades dos remedios cadastrados pelo usuario, uma checagem 1x1 de cada um se o complementos.py ou aquele remedio x já tiver uma incompatibilidade cadastrada daquela busca x o motor já devolve o resultado localmente, caso não tiver registros em incompatibilidades da comparação, ele aciona seu motor de busca usando IA para ter 100% de certeza que aquela comparação esta segura. 

## tratamento_csv_json.py
[tratamento_csv_json.py](core/tratamento_csv_json.py) serve unicamente para processar os dados de .csv do arquivo da [anvisa](data/medicamentos.csv) para .json com campos necessarios para a aplicação já que no csv tem muitos campos que não serão usados, fazendo até separação de dados, como identificar se o remedio x é um comprimido(solido), um liquido, como xarope, um injetavel, como a insulina humana NPH ou um colirio ou pegando tambem a dosagem do remedio em si. Usamos como db o [solidificados.json](data/solidificados.json), que, como descrito nas funçoes de cima é alto alimentado com as buscas dos campos de incompatibilidades e efeitos colaterais.

## ui_tratamento.py
Basicamente pega recebe os dados do bubble e modula de uma forma que o sistema reconheça e distribui para os responsaveis essa informação, estruturando o .json recebido e o completando, fazendo o match do nome fornecido com os remedios presentes no [solidificados.json](data/solidificados.json) usando regras e filtros para entregar um resultado mais coreto usando até mesmo em ultimo caso uma chamada na [ai_handler.py](core/ia/ai_handler.py) para buscar o nome fornecido e não encontrado no db, o mesmo faz as requisiçoes para [solidificados.json](data/solidificados.json) e [incompativeis.py](core/incompativeis.py). E quando o termina esses dados são levados de volta para o bubble

## teste_ai.py
[teste_ai.py](teste_ai.py) Serve apenas como teste de resposta do [ai_handler.py](core/ia/ai_handler.py)

# Comunicação Frontend x Backend via API

A comunicação é feita via apirest e usando ngrok. Quando o usuario completa o cadastro em de seu/s medicamentos e clica em finalizar cadastro, o bubble envia um .json para o python e o python processa esses dados, formata e devolve para o bubble.

# DB em .json e suas informações

O Banco de dados solidificados.json veio das informações da anvisa 
[CSV da Anvisa](https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO.csv) e usando uma [ferramenta para tratar esse csv](core/tratamento_csv_json.py) e transofrormar esse csv com dados que não iremos utilizar em um .json que passara a ser nosso banco de dados, o mesmo é preenchido dinamicamente quando o usuario faz um cadastro, os motores de pesquisa de incompatibilidade e complementos preenche os campos que estavam vazios ou os atualizando.

# Integração n8n com Telegram

Todos os dados que estão sendo usados no n8n esta passando pelo tuneu do ngrok, mais especificamente quando o python termina de processar os dados e retorna para o bubble e para o n8n

## Visão geral do n8n

![n8n_1](data/images/n8n/n8n_geral.png)

## Dados recebidos pelo n8n no primeiro webhook

![n8n_2](data/images/n8n/dados_post1.png)

## Condições do primeiro if

<img src="data/images/n8n/if1.png"  width="500">

## Em caso de else, erro

<img src="data/images/n8n/else1.png"  width="400">

## Condições do segundo if

<img src="data/images/n8n/if2.png"  width="500">

## http Request - para chamar o telegram

<img src="data/images/n8n/request_true.png"  width="400">

## Parametro para enviar a menssagem se true

<img src="data/images/n8n/request_true_parametros.png"  width="400">


## Devolvendo no telegra:

<img src="data/images/n8n/telegram.png" width="300">

# Frontend com Bubble

## Tela inicial/informativa

<img src="data/images/bubble/info_bubble1.png" width="700">
<img src="data/images/bubble/info_bubble2.png" width="700">
<img src="data/images/bubble/info_bubble3.png" width="700">
<img src="data/images/bubble/info_bubble4.png" width="700">

## Tela de login 

<img src="data/images/bubble/login1.png" width="400">
<img src="data/images/bubble/erro_emailsenha.png" width="400">

## Tela de cadastro

<img src="data/images/bubble/cadastro.png" width="400">

## Erro caso senha cadastrada != a confimação de senha

<img src="data/images/bubble/cadastro_senha_erro.png" width="600">

## Tela de navegação para usuario padrão = paciente, esquerda e tambem do cuidador à direita

<img src="data/images/bubble/navegação_paciente.png" width="300"><img src="data/images/bubble/navegação_cuidador.png" width="300">

navegação_cuidador.png
## Tela main inicial

<img src="data/images/bubble/main1.png" width="700">

<img src="data/images/bubble/main2.png" width="700">

## Tela de cadastro dos medicamentos

<img src="data/images/bubble/medicamentos1.png" width="700">

<img src="data/images/bubble/medicamentos2.png" width="300">
<img src="data/images/bubble/medicamentos3.png" width="300">
<img src="data/images/bubble/medicamentos4.png" width="300">

<img src="data/images/bubble/medicamentos5.png" width="700">
<img src="data/images/bubble/medicamentos6.png" width="700">

## Aqui enviaremos os dados para o python ele os processara e devolvera o resultado tanto para o n8n como para o Bubble, no caso, coloquei dois exemplares conflituosos é aqui que nosso motor brilha! 

<img src="data/images/bubble/medicamentos7.png" width="700">

## Voltando ao main/hoje, já temos os remedios que foram cadastrados, já com seu estoque,  horarios e marcado como pendencia.

<img src="data/images/bubble/main3.png" width="700">

## Já prontos para serem interagidos. nota. Remedio tomado já tem a subtração da quantidade de comprimidos tomados - estoque total

<img src="data/images/bubble/main4.png" width="325">
<img src="data/images/bubble/main5.png" width="325">
<img src="data/images/bubble/main6.png" width="325">

## Temos um sistema de edição para acrescentar ou mudar a quantidade de comprimidos a ser tomado

<img src="data/images/bubble/main7.png" width="325">

## Caso precise apagar algum remedio em questão, basta voltar no menu de medicamentos 

<img src="data/images/bubble/medicamentos8.png" width="700">
<img src="data/images/bubble/medicamentos9.png" width="300">

## Tambem podemos ver o seu historico das alterações feitas assim

<img src="data/images/bubble/historico1.png" width="325">
<img src="data/images/bubble/historico2.png" width="325">
<img src="data/images/bubble/historico3.png" width="325">

## Meu perfil

<img src="data/images/bubble/historico3.png" width="325">

## Em meu perfil, podemos tambem vincular a conta de paciente a uma de cuidador, usando o codigo de integração, ou, no caso, codigo para cuidador


<img src="data/images/bubble/profile1.png" width="700">

## Colando o codigo para cuidador no campo descrito em vincular codigo

<img src="data/images/bubble/cuidador1.png" width="700">

## Vinculado

<img src="data/images/bubble/cuidador2.png" width="700">

## Aqui esta a agenda e os remedios cadastrados do usuario teste

<img src="data/images/bubble/cuidador3.png" width="700">
<img src="data/images/bubble/cuidador4.png" width="700">
