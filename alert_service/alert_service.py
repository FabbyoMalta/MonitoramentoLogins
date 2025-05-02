import logging
import requests
import json
import os
from dotenv import load_dotenv

from flask import Flask, request, jsonify

load_dotenv()

os.makedirs("logs", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/app/logs/alert_service.log"),  # Log em arquivo
        logging.StreamHandler()                 # Log no terminal (stdout)
    ]
)
app = Flask(__name__)

# Configurações da API Gupshup (WhatsApp)
gupshup_app_name = os.getenv('GUPSHUP_APP_NAME')
gupshup_api_key = os.getenv('GUPSHUP_API_KEY')
gupshup_source_number = os.getenv('GUPSHUP_SOURCE_NUMBER')
gupshup_destination_numbers = os.getenv('GUPSHUP_DESTINATION_NUMBERS', '').split(',')
gupshup_template_id = os.getenv('GUPSHUP_TEMPLATE_ID')
gupshup_language = os.getenv('GUPSHUP_LANGUAGE', 'pt')

if not all([gupshup_app_name, gupshup_api_key, gupshup_source_number, gupshup_destination_numbers, gupshup_template_id]):
    logging.error("Variáveis de ambiente para a API Gupshup não definidas.")
    exit(1)

# Configurações do Telegram
telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

if not all([telegram_bot_token, telegram_chat_id]):
    logging.error("Variáveis de ambiente para o Telegram não definidas.")
    exit(1)

MAX_CLIENTS_IN_MESSAGE = 50

def send_telegram_alert(clientes, status, conexao, mensagem_personalizada=None):
    total_clientes = len(clientes)
    if total_clientes == 0:
        return {'message': 'Nenhum cliente para alertar'}
    
    if mensagem_personalizada:
        mensagem = mensagem_personalizada + "\n"
    elif status == 'offline':
        mensagem = f"🚨 *Alerta: {total_clientes} clientes offline detectados na conexão {conexao}.*\n"
    elif status == 'online':
        mensagem = f"✅ *Alerta: Todos os clientes voltaram a ficar online na conexão {conexao}.*\n"
    else:
        mensagem = f"*Alerta: {total_clientes} clientes com status desconhecido na conexão {conexao}.*\n"
    
    if total_clientes <= MAX_CLIENTS_IN_MESSAGE:
        for cliente in clientes:
            login = cliente.get('login', 'N/A')
            ultima_conexao_final = cliente.get('ultima_conexao_final', 'N/A')
            mensagem += f"- *Login:* `{login}`\n"
            mensagem += f"  *Última conexão:* {ultima_conexao_final}\n"
    else:
        mensagem += "Listando alguns clientes:\n"
        for cliente in clientes[:MAX_CLIENTS_IN_MESSAGE]:
            login = cliente.get('login', 'N/A')
            ultima_conexao_final = cliente.get('ultima_conexao_final', 'N/A')
            mensagem += f"- *Login:* `{login}`\n"
            mensagem += f"  *Última conexão:* {ultima_conexao_final}\n"
        mensagem += f"... e mais {total_clientes - MAX_CLIENTS_IN_MESSAGE} clientes."
    
    url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
    payload = {
        'chat_id': telegram_chat_id,
        'text': mensagem,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        logging.info("Alerta enviado com sucesso no Telegram.")
        return {'message': 'Alerta enviado com sucesso no Telegram'}
    except requests.exceptions.RequestException as e:
        logging.error(f"Falha ao enviar mensagem no Telegram: {e}")
        return {'error': str(e)}, 500

def send_whatsapp_alert(total_clientes, conexao, motivo):
    url = "https://api.gupshup.io/wa/api/v1/template/msg"
    headers_whatsapp = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'apikey': gupshup_api_key
    }

    # Passa os parâmetros na ordem correta do template
    template_params = [str(total_clientes), conexao, motivo]

    responses = []
    for destination_number in gupshup_destination_numbers:
        payload = {
            'source': gupshup_source_number,
            'destination': destination_number,
            'template': json.dumps({
                'id': gupshup_template_id,
                'params': template_params
            }),
            'channel': 'whatsapp',
            'message': '',
        }

        try:
            logging.info(f"Payload enviado para WhatsApp: {json.dumps(payload, indent=4)}")
            response = requests.post(url, data=payload, headers=headers_whatsapp)
            logging.info(f"Resposta da API WhatsApp: {response.status_code} - {response.text}")
            response.raise_for_status()

            data = response.json()
            if data.get('status') == 'submitted':
                logging.info(f"✅ WhatsApp enviado para {destination_number}")
                responses.append({'destination': destination_number, 'message': 'Enviado com sucesso'})
            else:
                logging.error(f"⚠️ Falha para {destination_number}: {data.get('message')}")
                responses.append({'destination': destination_number, 'error': data.get('message')})
        except requests.exceptions.RequestException as e:
            logging.error(f"Erro ao enviar mensagem via WhatsApp para {destination_number}: {e}")
            responses.append({'destination': destination_number, 'error': str(e)})

    return responses

@app.route('/alerta/telegram', methods=['POST'])
def alerta_telegram():
    data = request.get_json()
    clientes = data.get('clientes', [])
    status = data.get('status')
    conexao = data.get('conexao')
    mensagem_personalizada = data.get('mensagem_personalizada')
    result = send_telegram_alert(clientes, status, conexao, mensagem_personalizada)
    return jsonify(result)

@app.route('/alerta/whatsapp', methods=['POST'])
def alerta_whatsapp():
    data = request.get_json()
    total_clientes = data.get('total_clientes')
    conexao = data.get('conexao')
    motivo = data.get('motivo_final') or data.get('motivo')
    mensagem_personalizada = data.get('mensagem_personalizada')
    result = send_whatsapp_alert(total_clientes, conexao, motivo)
    return jsonify(result)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)
