#!/bin/bash
# RoomCurve - Start Script

cd "$(dirname "$0")"
export PYTHONPATH="$(pwd):$PYTHONPATH"

echo "🏠 RoomCurve - Raumsimulator nach DIN EN ISO 52016-1"
echo "================================"
echo ""
echo "Starte Streamlit Server..."
echo "Browser öffnet automatisch auf http://localhost:8501"
echo ""

streamlit run gui/app.py --server.headless true
