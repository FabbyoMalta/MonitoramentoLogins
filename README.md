# Monitor Service - PPPoE Event Tracker

Sistema de monitoramento de desconexões em massa de clientes PPPoE via API do IXCSoft, com integração de alerta por Telegram e WhatsApp, análise de motivo por OLT, e persistência de eventos em banco de dados SQLite.

---

## 📅 Funcionalidades

* Consulta clientes PPPoE online e offline via API do IXCSoft
* Detecta quedas em massa por conexão (OLT ou ponto de presença)
* Gera eventos persistentes (status: "ativo" ou "resolvido")
* Consulta OLT (via API externa) para identificar causa da queda
* Envia alertas por Telegram e WhatsApp
* Interface REST para consulta de eventos ativos

---

## 🚀 Como Funciona

1. A cada intervalo de tempo (por padrão 300s), o monitor consulta clientes online e offline
2. Compara com o estado anterior e identifica novos logins offline e logins reconectados
3. Para cada conexão com queda significativa:

   * Se não houver evento ativo, consulta OLT e gera novo evento persistente
   * Envia alertas com informações detalhadas
4. Quando todos os logins de um evento reconectarem:

   * Atualiza evento para "resolvido"
   * Envia alerta de normalização

---

## 📑 Requisitos

### Tecnologias utilizadas:

* Python 3.11+
* Flask
* Requests
* Python-dotenv
* SQLite3

### Ambiente:

* Docker (opcional, mas recomendado)
* API do IXCSoft acessível por HTTP
* API para envio de alertas (Telegram/WhatsApp) em funcionamento
* API para consulta a OLT

---

## 🌐 Variáveis de Ambiente (.env)

```env
THRESHOLD_OFFLINE_CLIENTS=4
MAX_CLIENTS_IN_MESSAGE=50
CHECK_INTERVAL=300

IXCSOFT_SERVICE_URL=http://localhost:5001
ALERT_SERVICE_URL=http://localhost:5002
OLT_SERVICE_URL=http://localhost:5003
```

---

## ⚙️ Executando o Monitor

### Localmente:

```bash
pip install -r requirements.txt
python monitor_service.py
```

### Via Docker:

```bash
docker build -t monitor_service .
docker run -p 5010:5010 --env-file .env monitor_service
```

---

## 🔎 API REST

### Listar eventos ativos

```
GET /eventos/ativos
```

**Resposta:**

```json
{
  "eventos_ativos": [
    {
      "id": "...",
      "conexao": "OLT-XYZ",
      "timestamp": 1714667890.0,
      "status": "ativo",
      "logins": ["cliente1", "cliente2"]
    }
  ]
}
```

---

## 📅 Estrutura do Banco de Dados

Banco: `monitor_events.db`

Tabela: `events`

| Campo     | Tipo | Descrição                       |
| --------- | ---- | ------------------------------- |
| id        | TEXT | UUID do evento                  |
| conexao   | TEXT | Nome da OLT/conexão             |
| timestamp | REAL | Epoch time da criação do evento |
| status    | TEXT | "ativo" ou "resolvido"          |
| logins    | TEXT | Lista JSON de logins afetados   |

---

## 🔧 Manutenção & Sugestões

* Verifique se não existem duas instâncias do monitor rodando (especialmente com `debug=True` no Flask).
* Para produção, utilize Gunicorn ou UWSGI para evitar múltiplas threads duplicadas com Flask.
* Logs em tempo real estão disponíveis em `logs/monitor_service.log`

---

## 🙌 Contribuições

Pull requests são bem-vindas! Sinta-se à vontade para sugerir melhorias, novos formatos de alerta, ou integrações com outras ferramentas (Zabbix, Grafana, etc).

---

**Autor:** Fabbyo Leão Malta

**Licença:** MIT
