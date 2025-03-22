import logging
import requests
import base64
import json
import os
from dotenv import load_dotenv
import urllib3

# Carregar variáveis de ambiente e configurar warnings
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)


# Obter configurações da API IXCSoft
host = os.getenv('IXCSOFT_HOST')
usuario = os.getenv('IXCSOFT_USUARIO')
token = os.getenv('IXCSOFT_TOKEN')

if not all([host, usuario, token]):
    logging.error("Variáveis de ambiente para a API IXCSoft não definidas.")
    exit(1)

token_usuario = f"{usuario}:{token}"
token_bytes = token_usuario.encode('utf-8')
token_base64 = base64.b64encode(token_bytes).decode('utf-8')

headers = {
    'Authorization': f'Basic {token_base64}',
    'Content-Type': 'application/json'
}

def fetch_clients():
    """
    status: 'online' ou 'offline'
    """
    url = f"https://{host}/webservice/v1/radusuarios"
    headers['ixcsoft'] = 'listar'
    
    clients = []
    page = 1
    rp = 1000  # registros por página

    payload = {
            #'grid_param': grid_param,
            'qtype': 'radusuarios.login',
            'query': 'duarte.julio',
            'oper': '=',
            'page': str(page),
            'rp': str(rp),
            'sortname': 'radusuarios.id',
            'sortorder': 'asc',
            #'login': 'duarte.julio',
        }
        

    response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False)
    response.raise_for_status()
    data = response.json()
            
    if 'type' in data and data['type'] == 'error':
        logging.error(f"Erro ao obter clientes: {data.get('message', '')}")
        
    registros = data.get('registros', [])
    total_registros = int(data.get('total', 0))

    with open('output_filtered.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print("Dados filtrados salvos com sucesso.")

    print(registros)
    return data

if __name__ == '__main__':
    fetch_clients()

