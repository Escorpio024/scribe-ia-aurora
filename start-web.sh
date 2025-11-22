#!/bin/bash

# Scribe-IA - Script de Inicio
# Este script inicia el servidor web para que funcione la grabación de audio

echo "🩺 Scribe-IA - Iniciando Servidor Web"
echo "======================================"
echo ""

# Verificar que estamos en el directorio correcto
if [ ! -d "web" ]; then
    echo "❌ Error: No se encuentra el directorio 'web'"
    echo "   Ejecuta este script desde el directorio raíz de scribe-ia"
    exit 1
fi

# Verificar que el servidor API esté corriendo
echo "🔍 Verificando servidor API..."
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    echo "✅ Servidor API corriendo en http://localhost:8080"
else
    echo "⚠️  Servidor API no detectado"
    echo "   Iniciando con docker compose..."
    docker compose up -d scribe_api
    echo "   Esperando 5 segundos..."
    sleep 5
fi

echo ""
echo "🚀 Iniciando servidor web en puerto 9000..."
echo ""
echo "📱 Abre tu navegador en:"
echo "   👉 http://localhost:9000/index.html"
echo ""
echo "📋 Flujo de uso:"
echo "   1. Admisión de paciente"
echo "   2. Selección de médico"
echo "   3. Grabación de consulta"
echo "   4. Generación automática de historia clínica"
echo ""
echo "⏹️  Presiona Ctrl+C para detener el servidor"
echo "======================================"
echo ""

cd web
python3 -m http.server 9000
