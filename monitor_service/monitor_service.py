import logging
import time
import json
import uuid
import requests
from dotenv import load_dotenv
import os
import threading
import sqlite3
from flask import Flask, request, jsonify

load_dotenv()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/monitor_service.log"),  # Log em arquivo
        logging.StreamHandler()                 # Log no terminal (stdout)
    ]
)

import sqlite3  # já está importado

def init_db():
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            conexao TEXT,
            timestamp REAL,
            status TEXT,
            logins TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_event(event, status):
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO events (id, conexao, timestamp, status, logins)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        event['id'],
        event.get('conexao', 'Desconhecida'),
        event.get('timestamp', time.time()),
        status,
        json.dumps(list(event.get('logins_offline', [])))
    ))
    conn.commit()
    conn.close()

def update_event_status(event_id, new_status):
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute('''
        UPDATE events SET status = ? WHERE id = ?
    ''', (new_status, event_id))
    conn.commit()
    conn.close()

def existe_evento_ativo_para_conexao(conexao):
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM events WHERE conexao = ? AND status = 'ativo'", (conexao,))
    count = c.fetchone()[0]
    conn.close()
    return count > 0

def carregar_eventos_ativos():
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute("SELECT id, conexao, timestamp, status, logins FROM events WHERE status = 'ativo'")
    eventos = []
    for row in c.fetchall():
        eventos.append({
            "id": row[0],
            "conexao": row[1],
            "timestamp": row[2],
            "status": row[3],
            "logins_offline": set(json.loads(row[4])),
            "logins_restantes": set(json.loads(row[4]))
        })
    conn.close()
    return eventos

# Parâmetros de configuração para monitoramento
THRESHOLD_OFFLINE_CLIENTS = int(os.getenv('THRESHOLD_OFFLINE_CLIENTS', 4))
MAX_CLIENTS_IN_MESSAGE = int(os.getenv('MAX_CLIENTS_IN_MESSAGE', 50))
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))  # 300 segundos = 5 minutos

# URLs dos microserviços (definidos via .env)
IXCSOFT_SERVICE_URL = os.getenv('IXCSOFT_SERVICE_URL', 'http://localhost:5001')
ALERT_SERVICE_URL = os.getenv('ALERT_SERVICE_URL', 'http://localhost:5002')
OLT_SERVICE_URL = os.getenv('OLT_SERVICE_URL', 'http://localhost:5003')

def get_clients(status):
    try:
        url = f"{IXCSOFT_SERVICE_URL}/clientes/{status}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get('clientes', [])
    except Exception as e:
        logging.error(f"Erro ao obter clientes {status}: {e}")
        return []

def send_telegram_alert(clientes, status, conexao, mensagem_personalizada=None):
    try:
        url = f"{ALERT_SERVICE_URL}/alerta/telegram"
        payload = {
            'clientes': clientes,
            'status': status,
            'conexao': conexao,
            'mensagem_personalizada': mensagem_personalizada
        }
        logging.info(f"Enviando alerta para {url} com payload: {json.dumps(payload)}")
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"Alerta enviado com sucesso para {conexao}. Status: {response.status_code}")
    except Exception as e:
        logging.critical(f"FALHA CRÍTICA ao enviar alerta para {ALERT_SERVICE_URL}/alerta/telegram. Erro: {e}. Payload: {json.dumps(payload)}")
        # TODO: Implementar mecanismo de retentativa ou notificação alternativa em caso de falha no envio do alerta.

def send_whatsapp_alert(total_clientes, conexao, motivo):
    try:
        url = f"{ALERT_SERVICE_URL}/alerta/whatsapp"
        payload = {
            'total_clientes': total_clientes,
            'conexao': conexao,
            'motivo': motivo
        }
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"Alerta WhatsApp enviado para conexão {conexao}.")
    except Exception as e:
        logging.error(f"Erro ao enviar alerta WhatsApp: {e}")

def monitor_connections():
    eventos_ativos = carregar_eventos_ativos()
    clientes_offline_anterior = set()
    clientes_info_offline_anterior = {}

    try:
        while True:
            logging.info("Iniciando verificação de clientes.")

            # Obter clientes offline atuais
            clientes_offline = get_clients('offline')
            clientes_offline_atual = set()
            clientes_info_offline_atual = {}
            for cliente in clientes_offline:
                login = cliente.get('login')
                clientes_offline_atual.add(login)
                clientes_info_offline_atual[login] = cliente

            # Obter clientes online atuais
            clientes_online = get_clients('online')
            clientes_online_atual = set()
            clientes_info_online_atual = {}
            for cliente in clientes_online:
                login = cliente.get('login')
                clientes_online_atual.add(login)
                clientes_info_online_atual[login] = cliente

            if clientes_offline_anterior:
                novos_offlines = clientes_offline_atual - clientes_offline_anterior
                clientes_reconectados = clientes_offline_anterior - clientes_offline_atual
                conexoes_novos_offlines = {}

                if novos_offlines:
                    logging.warning(f"Detectados {len(novos_offlines)} novos clientes offline.")
                    for login in novos_offlines:
                        cliente = clientes_info_offline_atual[login]
                        conexao = cliente.get('conexao', 'Desconhecida')
                        conexoes_novos_offlines.setdefault(conexao, []).append(cliente)

                for conexao, clientes in conexoes_novos_offlines.items():
                    if len(clientes) >= THRESHOLD_OFFLINE_CLIENTS:
                        if existe_evento_ativo_para_conexao(conexao):
                            # Encontrar o evento ativo para a conexão
                            evento_existente = None
                            for ev in eventos_ativos:
                                if ev['conexao'] == conexao:
                                    evento_existente = ev
                                    break
                            
                            if evento_existente:
                                novos_logins_nesta_conexao = set(cliente['login'] for cliente in clientes)
                                logging.info(f"Atualizando evento existente para conexão {conexao} com {len(novos_logins_nesta_conexao)} novos logins.")
                                
                                evento_existente['logins_offline'].update(novos_logins_nesta_conexao)
                                evento_existente['logins_restantes'].update(novos_logins_nesta_conexao)
                                
                                save_event(evento_existente, "ativo") # Persistir a atualização no banco de dados
                                logging.info(f"Evento {evento_existente['id']} atualizado no banco de dados com novos logins.")

                                # Preparar informações para alertas atualizados
                                # Para o Telegram, idealmente todos os clientes offline do evento
                                # Recriar a lista de clientes para o alerta do Telegram pode ser complexo aqui
                                # Vamos enviar detalhes dos *novos* clientes por enquanto, e a contagem total na mensagem
                                
                                mensagem_atualizacao_telegram = (
                                    f"🚨 🔄 *Atualização*: Mais {len(novos_logins_nesta_conexao)} clientes offline detectados na conexão {conexao}. "
                                    f"Total offline agora: {len(evento_existente['logins_restantes'])}."
                                )
                                # Para send_telegram_alert, 'clientes' deve ser uma lista de dicts
                                # Usaremos os 'clientes' recém detectados para esta conexão específica
                                send_telegram_alert(clientes, status='offline', conexao=conexao, mensagem_personalizada=mensagem_atualizacao_telegram)
                                
                                # Para WhatsApp, apenas a contagem e um motivo genérico
                                send_whatsapp_alert(len(evento_existente['logins_restantes']), conexao, "Atualização de evento")
                                continue # Pular para a próxima conexão após atualizar o evento existente
                            else:
                                logging.error(f"Evento ativo para conexão {conexao} não encontrado na lista eventos_ativos, embora existe_evento_ativo_para_conexao seja true. Isso não deveria acontecer.")
                                # Prosseguir para criar um novo evento como fallback, ou adicionar tratamento de erro específico

                        olt_logins = [cliente['login'] for cliente in clientes][:3]
                        if len(olt_logins) < 3:
                            logging.error("Não há logins suficientes para consulta à OLT.")
                            motivo = "indeterminado"
                        else:
                            id_transmissor = clientes[0].get('id_transmissor', 'OLT1')
                            olt_payload = {
                                "logins": olt_logins,
                                "id_transmissor": id_transmissor
                            }
                            try:
                                response = requests.post(f"{OLT_SERVICE_URL}/consulta/olt", json=olt_payload)
                                response.raise_for_status()
                                motivo = response.json().get("motivo_final", "indeterminado")
                            except Exception as e:
                                logging.error(f"Erro ao consultar OLT: {e}")
                                motivo = "indeterminado"

                        evento = {
                            'id': str(uuid.uuid4()),
                            'conexao': conexao,
                            'logins_offline': set(cliente['login'] for cliente in clientes),
                            'logins_restantes': set(cliente['login'] for cliente in clientes),
                            'timestamp': time.time()
                        }

                        eventos_ativos.append(evento)
                        save_event(evento, "ativo")
                        logging.info(f"Criado novo evento {evento['id']} para conexão {conexao} com {len(clientes)} logins offline.")

                        mensagem_alerta = (
                            f"🚨 *Alerta: {len(clientes)} clientes offline detectados na conexão {conexao}.*\n"
                            f"Motivo da queda: {motivo.capitalize()}"
                        )

                        # --- BEGIN Address Fetching Logic for New Event ---
                        logging.info(f"Fetching addresses for up to 20 clients for new event in conexao {conexao}")
                        clients_for_address_lookup = clientes[:20] # Get the first 20 clients

                        # This loop modifies the dictionaries within the 'clientes' list directly.
                        for client_to_lookup in clients_for_address_lookup:
                            client_id = client_to_lookup.get('id_cliente')
                            login_for_log = client_to_lookup.get('login', 'N/A') # For logging

                            if client_id:
                                address_url = f"{IXCSOFT_SERVICE_URL}/cliente/{client_id}"
                                try:
                                    # Assuming ixcsoft_service endpoint /cliente/{id} does not require special headers beyond what requests might send by default
                                    # or that ixcsoft_service is not behind a gateway that needs specific auth for this internal call.
                                    # If ixcsoft_service expects the same auth as its own external calls, headers would be needed.
                                    # For now, let's assume no special headers are needed for this internal service-to-service call.
                                    response = requests.get(address_url, timeout=5) # Added timeout
                                    response.raise_for_status()
                                    address_data = response.json()

                                    client_to_lookup['bairro'] = address_data.get('bairro')
                                    client_to_lookup['endereco'] = address_data.get('endereco')
                                    logging.info(f"Successfully fetched address for client ID {client_id} (Login: {login_for_log}): Bairro - {client_to_lookup['bairro']}, Endereco - {client_to_lookup['endereco']}")

                                except requests.exceptions.RequestException as e:
                                    logging.error(f"Error fetching address for client ID {client_id} (Login: {login_for_log}): {e}")
                                    client_to_lookup['bairro'] = None
                                    client_to_lookup['endereco'] = None
                                except json.JSONDecodeError as e:
                                    logging.error(f"Error decoding JSON for client ID {client_id} (Login: {login_for_log}): {e}. Response text: {response.text if 'response' in locals() else 'N/A'}")
                                    client_to_lookup['bairro'] = None
                                    client_to_lookup['endereco'] = None
                                except Exception as e: # Catch any other unexpected error
                                    logging.error(f"Unexpected error fetching address for client ID {client_id} (Login: {login_for_log}): {e}")
                                    client_to_lookup['bairro'] = None
                                    client_to_lookup['endereco'] = None
                            else:
                                logging.warning(f"Client login {login_for_log} is missing 'id_cliente'. Cannot fetch address.")
                                client_to_lookup['bairro'] = None
                                client_to_lookup['endereco'] = None
                        # --- END Address Fetching Logic ---

                        # 'clientes' list now contains updated address info for the first 20 clients
                        send_telegram_alert(clientes, status='offline', conexao=conexao, mensagem_personalizada=mensagem_alerta)
                        send_whatsapp_alert(len(clientes), conexao, motivo)
                    else:
                        logging.info(f"Offline insuficiente para alerta na conexão {conexao} ({len(clientes)}).")

                if clientes_reconectados:
                    logging.info(f"{len(clientes_reconectados)} clientes voltaram a ficar online.")
                    eventos_para_remover = []
                    for login in clientes_reconectados:
                        for evento in eventos_ativos:
                            if login in evento['logins_restantes']:
                                evento['logins_restantes'].remove(login)
                                if not evento['logins_restantes']:
                                    clientes_evento = [clientes_info_online_atual.get(l, {'login': l}) for l in evento['logins_offline']]
                                    send_telegram_alert(clientes_evento, status='online', conexao=evento['conexao'])
                                    update_event_status(evento['id'], "resolvido")
                                    eventos_para_remover.append(evento)
                    for evento in eventos_para_remover:
                        eventos_ativos.remove(evento)

            else:
                logging.info("Primeira execução: inicializando estados.")

            clientes_offline_anterior = clientes_offline_atual
            clientes_info_offline_anterior = clientes_info_offline_atual

            logging.info(f"Aguardando {CHECK_INTERVAL} segundos para a próxima verificação.")
            time.sleep(CHECK_INTERVAL)

    except KeyboardInterrupt:
        logging.info("Monitoramento interrompido manualmente.")


# --------------------------------------------------
# API REST para consultar eventos ativos
# --------------------------------------------------

app = Flask(__name__)

@app.route('/eventos/ativos', methods=['GET'])
def get_eventos_ativos():
    conn = sqlite3.connect("monitor_events.db")
    c = conn.cursor()
    c.execute("SELECT id, conexao, timestamp, status, logins FROM events WHERE status = 'ativo'")
    eventos = c.fetchall()
    conn.close()

    eventos_formatados = []
    for evento in eventos:
        eventos_formatados.append({
            "id": evento[0],
            "conexao": evento[1],
            "timestamp": evento[2],
            "status": evento[3],
            "logins": json.loads(evento[4])
        })

    return jsonify({"eventos_ativos": eventos_formatados})


# --------------------------------------------------
# Execução do Monitor Service com API
# --------------------------------------------------

def start_monitoring():
    monitor_connections()

if __name__ == '__main__':
    init_db()
    logging.info("Iniciando o serviço de monitoramento de conexões.")
    
    # Garante que monitor_connections só roda no processo principal
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        monitor_thread = threading.Thread(target=start_monitoring, daemon=True)
        monitor_thread.start()
    
    app.run(host='0.0.0.0', port=5010, debug=True)
