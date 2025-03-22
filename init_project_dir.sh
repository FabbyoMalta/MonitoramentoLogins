#!/bin/bash

# Nome do microserviço (passado como argumento)
SERVICE_NAME=$1

if [ -z "$SERVICE_NAME" ]; then
  echo "Uso: ./init_project.sh nome_do_servico"
  exit 1
fi

mkdir -p $SERVICE_NAME/app

# Cria arquivos principais
touch $SERVICE_NAME/app/__init__.py
touch $SERVICE_NAME/app/routes.py
touch $SERVICE_NAME/app/services.py
touch $SERVICE_NAME/app/utils.py
touch $SERVICE_NAME/config.py
touch $SERVICE_NAME/requirements.txt
touch $SERVICE_NAME/Dockerfile
touch $SERVICE_NAME/.env.example
touch $SERVICE_NAME/.dockerignore

echo -e "# ${SERVICE_NAME^}\nEstrutura básica criada com sucesso."

