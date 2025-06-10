import logging
import requests
import base64
import json
import os
from dotenv import load_dotenv
import urllib3

from flask import Flask, request, jsonify

# Carregar variáveis de ambiente e configurar warnings
load_dotenv()
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/ixcsoft_service.log"),  # Log em arquivo
        logging.StreamHandler()                 # Log no terminal (stdout)
    ]
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

def fetch_client_address(client_id):
    """
    Busca o endereço (bairro e rua) de um cliente específico na API IXCSoft.
    """
    url = f"https://{host}/webservice/v1/cliente/{client_id}"
    # headers_get = headers.copy()  # Copia para não modificar o global
    # headers_get.pop('ixcsoft', None) # GET request might not need 'ixcsoft' header or it might be different

    try:
        response = requests.get(url, headers=headers, verify=False) # Assuming GET for individual client
        response.raise_for_status()
        data = response.json()

        if 'type' in data and data['type'] == 'error':
            logging.error(f"Erro ao obter endereço para o cliente {client_id}: {data.get('message', '')}")
            return None

        # Extrair bairro e endereço da resposta
        # Ajuste os campos conforme a estrutura real da resposta da API para /cliente/{id}
        address_info = {
            'bairro': data.get('bairro'),
            'endereco': data.get('endereco')
        }
        logging.info(f"Endereço obtido para cliente {client_id}: Bairro - {address_info['bairro']}, Endereço - {address_info['endereco']}")
        return address_info

    except requests.exceptions.RequestException as e:
        logging.error(f"Erro na requisição de endereço para o cliente {client_id}: {e}")
        return None
    except json.JSONDecodeError:
        logging.error(f"Erro ao decodificar JSON da resposta de endereço para o cliente {client_id}.")
        return None

app = Flask(__name__)

def resume_os(setor):
    url = f"https://{host}/webservice/v1/su_oss_chamado"
    headers['ixcsoft'] = 'listar'

    os_abertas = []
    os_fechadas = []
    page = 1
    rp = 1000  # registros por página    

    setor == 'instalacao':
        grid_param = json.dumps([
            {"TB": "su_oss_chamado.assunto", "OP": "!=",   }
        ])




def fetch_clients(status):
    """
    status: 'online' ou 'offline'
    """
    url = f"https://{host}/webservice/v1/radusuarios"
    headers['ixcsoft'] = 'listar'
    
    clients = []
    page = 1
    rp = 1000  # registros por página
    
    if status == 'offline':
        grid_param = json.dumps([
            {"TB": "radusuarios.ativo", "OP": "=", "P": "S"},
            {"TB": "radusuarios.online", "OP": "=", "P": "N"}
        ])
    elif status == 'online':
        grid_param = json.dumps([
            {"TB": "radusuarios.ativo", "OP": "=", "P": "S"},
            {"TB": "radusuarios.online", "OP": "=", "P": "S"}
        ])
    else:
        return []
    
    while True:
        payload = {
            'grid_param': grid_param,
            'page': str(page),
            'rp': str(rp),
            'sortname': 'radusuarios.id',
            'sortorder': 'asc'
        }
        
        try:
            response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False)
            response.raise_for_status()
            data = response.json()
            
            if 'type' in data and data['type'] == 'error':
                logging.error(f"Erro ao obter clientes {status}: {data.get('message', '')}")
                break
            
            registros = data.get('registros', [])
            total_registros = int(data.get('total', 0))
            
            for registro in registros:
                client_info = {
                    'id_cliente': registro.get('id_cliente'),
                    'login': registro.get('login'),
                    'conexao': registro.get('conexao'),
                    'ultima_conexao_final': registro.get('ultima_conexao_final'),
                    'id_transmissor': registro.get('id_transmissor'),
                    'latitude': registro.get('latitude'),
                    'longitude': registro.get('longitude')
                }

                # Buscar endereço do cliente
                id_cliente = registro.get('id_cliente')
                if id_cliente:
                    address_data = fetch_client_address(id_cliente)
                    if address_data:
                        client_info['bairro'] = address_data.get('bairro')
                        client_info['endereco'] = address_data.get('endereco')
                    else:
                        client_info['bairro'] = None
                        client_info['endereco'] = None
                else:
                    client_info['bairro'] = None
                    client_info['endereco'] = None
                    logging.warning(f"Cliente com registro {registro.get('id')} não possui 'id_cliente'.")

                clients.append(client_info)
            
            logging.info(f"Página {page}: Obtidos {len(registros)} registros de clientes {status}.")
            
            if len(clients) >= total_registros or len(registros) == 0:
                break
            else:
                page += 1
                
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro na requisição à API IXCSoft: {e}")
            break
    logging.info(f"Total de clientes {status} obtidos: {len(clients)}")
    return clients

@app.route('/clientes/offline', methods=['GET'])
def get_offline_clients():
    clients = fetch_clients('offline')
    return jsonify({'clientes': clients})

@app.route('/clientes/online', methods=['GET'])
def get_online_clients():
    clients = fetch_clients('online')
    return jsonify({'clientes': clients})

@app.route('/saida_api', methods=['GET'])
def salvar_saida_api():
    """
    Endpoint para depuração: retorna a saída da API (primeira página) sem salvar em arquivo.
    """
    url = f"https://{host}/webservice/v1/radusuarios"
    headers['ixcsoft'] = 'listar'
    grid_param = json.dumps([
            {"TB": "radusuarios.ativo", "OP": "=", "P": "S"},
            {"TB": "radusuarios.online", "OP": "=", "P": "N"}
        ])
    payload = {
            'grid_param': grid_param,
            'page': '1',
            'rp': '1000',
            'sortname': 'radusuarios.id',
            'sortorder': 'asc'
        }
    try:
        response = requests.post(url, data=json.dumps(payload), headers=headers, verify=False)
        response.raise_for_status()
        data = response.json()
        return jsonify(data)
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro na requisição à API IXCSoft: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
