import logging
import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
MONITOR_SERVICE_URL = os.getenv('MONITOR_SERVICE_URL', 'http://monitor_service:5010')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
)

# Comando /listar_eventos
async def listar_eventos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        response = requests.get(f"{MONITOR_SERVICE_URL}/eventos/ativos")
        response.raise_for_status()
        data = response.json()
        eventos = data.get("eventos_ativos", [])

        if not eventos:
            await update.message.reply_text("✅ Nenhum evento ativo no momento.")
            return

        mensagem = "📡 *Eventos Ativos:*\n"
        for evento in eventos:
            horario = datetime.fromtimestamp(evento["timestamp"]).strftime("%d/%m %H:%M")
            mensagem += (
                f"🆔 *ID:* `{evento['id'][:8]}...`\n"
                f"🔌 *Conexão:* {evento['conexao']}\n"
                f"⏱ *Horário:* {horario}\n"
                f"👥 *Clientes Offline:* {len(evento['logins'])}\n\n"
            )

        await update.message.reply_text(mensagem, parse_mode="Markdown")

    except Exception as e:
        logging.error(f"Erro ao consultar eventos: {e}")
        await update.message.reply_text("❌ Erro ao consultar os eventos ativos.")

# Inicializa o bot
def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("listar_eventos", listar_eventos))
    app.run_polling()

if __name__ == "__main__":
    main()
