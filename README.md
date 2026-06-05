# Automação para baixar DCTF e PERDCOMPS

## Pré-requisitos
- Python 3.12+
- Certificado (.pfx) da empresa que deseja fazer a baixa
- VENV, com as bibliotecas necessárioas

## Etapas
1. Execute o arquivo `gerador_sessao.py`.
2. Após abrir o navegador, faça login manualmente para empresa que deseja, usando o certificado. Se for por procuração, fazer o login com o certificado do procurador, e clicar no menu e acessar a procuração para a empresa.
3. Depois de logado, aguarde o navegador encerrar sozinho.
4. Ele vai gerar um arquivo chamado `cookies.json`, dentro da pasta `temp`.
5. Execute o arquivo `baixar_dctf.py`.
6. Ele vai realizar a baixa dos arquivos dctf, e depois perdcomps.
7. No final, ele vai gerar pastas para cada grupo de arquivos.

## VENV
- Para criar uma venv e instalar as bibliotecas necessárias, siga os passos a seguir:
1. execute no terminal: `python -m venv ./venv`
2. em seguida execute no mesmo terminal: `pip install -r requirements.txt`
