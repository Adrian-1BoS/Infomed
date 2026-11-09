# Infomed

![Logo infomed](https://gestlreythduxcbqprab.supabase.co/storage/v1/object/public/logos/120afd64-6911-4e54-81ab-1e656e3c5037-1789168844649.jfif)

O Infomed é uma plataforma de gestão de estoque e triagem de compatibilidade. Podendo ser usado por 1 pessoa ou 1 cuidador que gerencia os medicamentos de seus pacientes.

## Frontend com bubble



## Backend com python

No Python, temos alguns motores;

### app.py


### ai_handler.py
[ai_handler.py](core/ia/ai_handler.py) basicamente é o aquivo de chamada/comunicação com as ias do [google](https://aistudio.google.com) e do [groq](https://console.groq.com) (configure suas apis em .env.example) se uma não retornar ou falhar no meio do caminho, a outra continua de onde parou. Servindo principalmete para receber e devolver prompts, se ja tiver configurado seu .env, pode utilizar o teste_ai.py para ver se retornam.

### complementos.py
[complementos.py](core/complementos.py) ele busca os dados no [db](data/solidificados.json) e se tiver dados fatando, ele complementa os dados de capos imcompatibilidades e efeitos colaterais que veio da requisição do remedio x usando prompt de contexto e os de busca, veja em prompt_farmaceutico; montado para encaixotar o que veio da UI o maximo possivel para entregar o melhor resultado no match.

### incompativeis.py
[incompativeis.py](core/incompativeis.py) aqui se inicia a checagem de incompatibilidades dos remedios cadastrados pelo usuario, uma checagem 1x1 de cada um se o complementos.py ou aquele remedio x já tiver uma incompatibilidade cadastrada daquela busca x o motor já devolve o resultado localmente, caso não tiver registros em incompatibilidades da comparação, ele aciona seu motor de busca usando IA para ter 100% de certeza que aquela comparação esta segura. 

### tratamento_csv_json.py
[tratamento_csv_json.py](core/tratamento_csv_json.py) serve unicamente para processar os dados de .csv do arquivo da [anvisa](data/medicamentos.csv) para .json com campos necessarios para a aplicação já que no csv tem muitos campos que não serão usados, fazendo até separação de dados, como identificar se o remedio x é um comprimido(solido), um liquido, como xarope, um injetavel, como a insulina humana NPH ou um colirio ou pegando tambem a dosagem do remedio em si. Usamos como db o [solidificados.json](data/solidificados.json), que, como descrito nas funçoes de cima é alto alimentado com as buscas dos campos de incompatibilidades e efeitos colaterais.

### ui_tratamento.py
Basicamente pega recebe os dados do bubble e modula de uma forma que o sistema reconheça e distribui para os responsaveis essa informação, estruturando o .json recebido e o completando, fazendo o match do nome fornecido com os remedios presentes no [solidificados.json](data/solidificados.json) usando regras e filtros para entregar um resultado mais coreto usando até mesmo em ultimo caso uma chamada na [ai_handler.py](core/ia/ai_handler.py) para buscar o nome fornecido e não encontrado no db, o mesmo faz as requisiçoes para [solidificados.json](data/solidificados.json) e [incompativeis.py](core/incompativeis.py). E quando o termina esses dados são levados de volta para o bubble

### teste_ai.py
[teste_ai.py](teste_ai.py) Serve apenas como teste de resposta do [ai_handler.py](core/ia/ai_handler.py)


## Logs de erros com n8n


## Comunicação Frontend x Backend via API

A comunicação é feita via apirest e usando ngrok. Quando o usuario completa o cadastro em de seu/s medicamentos e clica em finalizar cadastro, o bubble envia um .json para o python e o python processa esses dados, formata e devolve para o bubble.

## DB em .json e suas informações

O Banco de dados solidificados.json veio das informações da anvisa 
[CSV da Anvisa](https://dados.anvisa.gov.br/dados/TA_PRECO_MEDICAMENTO.csv) e usando uma [ferramenta para tratar esse csv](core/tratamento_csv_json.py) e transofrormar esse csv com dados que não iremos utilizar em um .json que passara a ser nosso banco de dados, o mesmo é preenchido dinamicamente quando o usuario faz um cadastro, os motores de pesquisa de incompatibilidade e complementos preenche os campos que estavam vazios ou os atualizando.
