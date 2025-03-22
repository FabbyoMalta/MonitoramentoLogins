import os
import re
import time
import logging
import paramiko
from flask import Flask, request, jsonify
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

app = Flask(__name__)

# Configurações de acesso SSH para a OLT (exceto o IP, que será determinado dinamicamente)
OLT_SSH_PORT = int(os.getenv("OLT_SSH_PORT", "22"))
OLT_USERNAME = os.getenv("OLT_USERNAME")
OLT_PASSWORD = os.getenv("OLT_PASSWORD")
OLT_COMMAND = os.getenv("OLT_COMMAND", "display ont info by-desc")  # Base do comando

if not all([OLT_USERNAME, OLT_PASSWORD]):
    logging.error("Variáveis de ambiente para a conexão SSH com a OLT não estão definidas.")
    exit(1)

# Mapeamento de id_transmissor para IP da OLT
OLT_IP_MAPPING = {
    "1": "10.1.10.14",
    "5": "10.200.10.14",
    "6": "10.200.10.10"
}

def query_olt_single_login(login, olt_ip):
    """
    Consulta a OLT para um único login.
    1. SSH -> enable -> config -> display ont info by-desc <login>
    2. Extrai F/S/P + ONT-ID
    3. Para cada par, executa display ont info <frame> <slot> <pon> <ont_id>
       e extrai "Last down cause".
    4. Determina o 'motivo' para esse login:
       - Se houver "dying-gasp", motivo = "energia"
       - Se houver "LOSi/LOBi" ou "LOFi", motivo = "loss"
       - Caso contrário, "indeterminado"
    Retorna (motivo, detalhes)
    onde 'detalhes' é uma lista de dicionários com:
      {
        "fspon": "0/1/0",
        "ont_id": "0",
        "last_down_cause": "...",
      }
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            olt_ip,
            port=OLT_SSH_PORT,
            username=OLT_USERNAME,
            password=OLT_PASSWORD,
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        channel = client.invoke_shell()
        time.sleep(1)

        # Enviar comandos iniciais
        comandos_iniciais = [
            "enable",
            "config",
            f"{OLT_COMMAND} {login}"
        ]
        full_output = ""
        for cmd in comandos_iniciais:
            logging.info(f"Enviando comando: {cmd}")
            channel.send(cmd + "\n")
            time.sleep(2)
            while channel.recv_ready():
                full_output += channel.recv(1024).decode("utf-8")

        logging.info(f"Saída do comando '{OLT_COMMAND} {login}':\n{full_output}")

        # Extrair F/S/P e ONT-ID (com tolerância a espaços)
        matches = re.findall(
            r"(?m)^\s*(\d+\s*/\s*\d+\s*/\s*\d+)\s+(\d+)\s+",
            full_output
        )
        if not matches:
            logging.error("Não foi possível extrair F/S/P e ONT-ID da saída.")
            return ("indeterminado", [])

        # Remove duplicados
        unique_matches = list({(fspon_raw.replace(" ", ""), ont_id) for fspon_raw, ont_id in matches})

        # Agora, para cada par, obtemos o "Last down cause"
        details = []
        for fspon, ont_id in unique_matches:
            partes = fspon.split("/")
            if len(partes) != 3:
                logging.error(f"Formato inválido de F/S/P: {fspon}")
                continue
            frame, slot, pon = partes
            cmd_quarto = f"display ont info {frame} {slot} {pon} {ont_id}"
            logging.info(f"Enviando comando: {cmd_quarto}")
            channel.send(cmd_quarto + "\n")
            time.sleep(2)

            output_cmd4 = ""
            while channel.recv_ready():
                output_cmd4 += channel.recv(1024).decode("utf-8")

            logging.info("Saída do quarto comando obtida.")
            cause_match = re.search(r"Last down cause\s*:\s*(.+)", output_cmd4)
            if cause_match:
                last_down_cause = cause_match.group(1).strip()
            else:
                last_down_cause = "indeterminado"

            details.append({
                "fspon": fspon,
                "ont_id": ont_id,
                "last_down_cause": last_down_cause
            })

        # Agregar o motivo para ESTE login
        # Se houver "dying-gasp" => "energia"
        # Se houver "LOSi/LOBi" ou "LOFi" => "loss"
        # Caso contrário => "indeterminado"
        has_energia = any("dying-gasp" in d["last_down_cause"].lower() for d in details)
        has_loss = any(x in d["last_down_cause"].upper() for d in details for x in ["LOSI/LOBI", "LOFI"])

        if has_energia:
            final_motivo = "energia"
        elif has_loss:
            final_motivo = "loss"
        else:
            final_motivo = "indeterminado"

        return (final_motivo, details)

    except Exception as e:
        logging.error(f"Erro na consulta à OLT: {e}")
        return ("indeterminado", [])
    finally:
        client.close()

def consult_olt_multiple_logins(logins, olt_ip):
    """
    Para cada login na lista:
      - Chama query_olt_single_login(login, olt_ip)
      - Soma contagem de energia e loss
    Retorna o motivo final (por maioria) e os detalhes de cada login.
    """
    energy_count = 0
    loss_count = 0
    all_details = []

    for login in logins:
        motivo_login, details = query_olt_single_login(login, olt_ip)
        all_details.append({
            "login": login,
            "motivo": motivo_login,
            "details": details
        })
        if motivo_login == "energia":
            energy_count += 1
        elif motivo_login == "loss":
            loss_count += 1

    # Decisão por maioria (2 ou mais)
    if energy_count >= 2:
        final = "energia"
    elif loss_count >= 2:
        final = "loss"
    else:
        final = "indeterminado"

    return final, all_details

@app.route('/consulta/olt', methods=['POST'])
def consulta_olt_endpoint():
    """
    Endpoint que recebe um JSON com:
      - "logins": lista de logins (3 ou mais)
      - "id_transmissor": qual OLT consultar
    Faz a consulta para cada login e decide o motivo final por maioria.
    """
    data = request.get_json()

    logins = data.get("logins", [])
    id_transmissor = data.get("id_transmissor")
    logging.info(f"Payload recebido no OLT Service: {data}")
    if not logins or len(logins) < 1:
        return jsonify({"error": "Ao menos um login é necessário."}), 400
    if not id_transmissor:
        return jsonify({"error": "O campo id_transmissor é obrigatório."}), 400

    olt_ip = OLT_IP_MAPPING.get(id_transmissor)
    if not olt_ip:
        return jsonify({"error": f"ID da OLT desconhecido: {id_transmissor}."}), 400

    logging.info(f"Iniciando consulta na OLT {olt_ip} para os logins: {logins}")
    final_motivo, all_details = consult_olt_multiple_logins(logins, olt_ip)

    return jsonify({
        "motivo_final": final_motivo,
        "detalhes": all_details
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)