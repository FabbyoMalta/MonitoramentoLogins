import logging
import time
import json
import uuid
import requests
from dotenv import load_dotenv
import os

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
        response = requests.post(url, json=payload)
        response.raise_for_status()
        logging.info(f"Alerta Telegram enviado para conexão {conexao}.")
    except Exception as e:
        logging.error(f"Erro ao enviar alerta Telegram: {e}")

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
    clientes_offline_anterior = set()
    clientes_info_offline_anterior = {}
    eventos_ativos = []  # Lista de eventos ativos

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
                # Identificar novos clientes offline e reconexões
                novos_offlines = clientes_offline_atual - clientes_offline_anterior
                clientes_reconectados = clientes_offline_anterior - clientes_offline_atual
                conexoes_novos_offlines = {}

                if novos_offlines:
                    logging.warning(f"Detectados {len(novos_offlines)} novos clientes offline.")
                    # Agrupar novos offlines por 'conexao'
                    conexoes_novos_offlines = {}
                    for login in novos_offlines:
                        cliente = clientes_info_offline_atual[login]
                        conexao = cliente.get('conexao', 'Desconhecida')
                        conexoes_novos_offlines.setdefault(conexao, []).append(cliente)
                    
                # Dentro do laço que processa os novos clientes offline (dentro do for de conexões):
                for conexao, clientes in conexoes_novos_offlines.items():
                    if len(clientes) >= THRESHOLD_OFFLINE_CLIENTS:
                        # Obtenha até 3 logins para consulta à OLT
                        olt_logins = [cliente['login'] for cliente in clientes][:3]
                        # Verifica se temos 3 logins; se não, define motivo como indeterminado.
                        if len(olt_logins) < 3:
                            logging.error("Não há logins suficientes para consulta à OLT. Necessário pelo menos 3 logins.")
                            motivo = "indeterminado"
                        else:
                            # Obtém o id_transmissor do primeiro cliente (ou define padrão 'OLT1')
                            id_transmissor = clientes[0].get('id_transmissor', 'OLT1')
                            olt_payload = {
                                "logins": olt_logins,
                                "id_transmissor": id_transmissor
                            }
                            logging.info(f"Payload para OLT: {olt_payload}")
                            try:
                                olt_response = requests.post(f"{OLT_SERVICE_URL}/consulta/olt", json=olt_payload)
                                olt_response.raise_for_status()
                                logging.info(f"Resposta do OLT Service: {olt_response.text}")
                                motivo = olt_response.json().get("motivo_final")
                            except Exception as e:
                                logging.error(f"Erro ao consultar OLT: {e}")
                                motivo = "indeterminado"

                        # Cria novo evento
                        evento = {
                            'id': str(uuid.uuid4()),
                            'conexao': conexao,
                            'logins_offline': set(cliente['login'] for cliente in clientes),
                            'logins_restantes': set(cliente['login'] for cliente in clientes),
                            'timestamp': time.time()
                        }
                        eventos_ativos.append(evento)
                        logging.info(f"Criado novo evento {evento['id']} para conexão {conexao} com {len(clientes)} logins offline.")

                        # Monta a mensagem de alerta com o motivo final da queda
                        mensagem_alerta = (
                            f"🚨 *Alerta: {len(clientes)} clientes offline detectados na conexão {conexao}.*\n"
                            f"Motivo da queda: {motivo.capitalize()}"
                        )
                        send_telegram_alert(clientes, status='offline', conexao=conexao, mensagem_personalizada=mensagem_alerta)
                        send_whatsapp_alert(
                            total_clientes=len(clientes),
                            conexao=conexao,
                            motivo=motivo  # <- novo parâmetro correto!
                        )

                    else:
                        logging.info(f"Número de novos clientes offline na conexão {conexao} ({len(clientes)}) abaixo do limite de alerta.")

                else:
                    logging.info("Nenhum novo cliente offline detectado.")

                if clientes_reconectados:
                    logging.info(f"Detectados {len(clientes_reconectados)} clientes que voltaram a ficar online.")
                    for login in clientes_reconectados:
                        eventos_para_remover = []
                        for evento in eventos_ativos:
                            if login in evento['logins_restantes']:
                                evento['logins_restantes'].remove(login)
                                logging.info(f"Login {login} reconectado no evento {evento['id']}.")
                                if not evento['logins_restantes']:
                                    logging.info(f"Todos os logins do evento {evento['id']} reconectaram.")
                                    clientes_evento = [clientes_info_online_atual.get(l, {'login': l}) for l in evento['logins_offline']]
                                    send_telegram_alert(clientes_evento, status='online', conexao=evento['conexao'])
                                    eventos_para_remover.append(evento)
                        for evento in eventos_para_remover:
                            eventos_ativos.remove(evento)
                else:
                    logging.info("Nenhum cliente reconectado detectado.")
            else:
                logging.info("Primeira execução: inicializando listas de clientes.")

            clientes_offline_anterior = clientes_offline_atual
            clientes_info_offline_anterior = clientes_info_offline_atual

            logging.info(f"Aguardando {CHECK_INTERVAL} segundos para a próxima verificação.")
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logging.info("Interrupção solicitada pelo usuário. Encerrando o monitoramento de conexões.")

if __name__ == '__main__':
    logging.info("Iniciando o serviço de monitoramento de conexões.")
    monitor_connections()
