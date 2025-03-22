import paramiko
import logging

logging.basicConfig(level=logging.INFO)
olt_ip = "192.168.1.100"  # IP da OLT para testar
olt_port = 22
username = "seu_usuario_olt"
password = "sua_senha_olt"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

try:
    client.connect(
        olt_ip,
        port=olt_port,
        username=username,
        password=password,
        timeout=10,
        look_for_keys=False,
        allow_agent=False
    )
    logging.info("Conexão SSH estabelecida com sucesso!")
except Exception as e:
    logging.error(f"Erro ao conectar: {e}")
finally:
    client.close()