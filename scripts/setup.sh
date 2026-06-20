#!/bin/bash
# Aerumentis — Development Setup Script
set -e
echo "🛫 Aerumentis — Development Setup"
echo "================================"
PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "Python version: $PYTHON_VERSION"
if python3 -c 'import sys; assert sys.version_info >= (3, 11)' 2>/dev/null; then
    echo "✅ Python 3.11+ detected"
else
    echo "❌ Python 3.11+ required. Found $PYTHON_VERSION"
    exit 1
fi
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate
echo "📥 Upgrading pip..."
pip install --upgrade pip setuptools wheel
echo "📥 Installing Aerumentis with dev dependencies..."
pip install -e ".[dev]"
if [ ! -f .env ]; then
    echo ""
    echo "⚙️  Creating .env from .env.example..."
    cp .env.example .env
    echo "✅ .env created — edit it to add your API keys"
else
    echo "✅ .env already exists"
fi
mkdir -p storage
echo ""
echo "================================"
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your OPENAI_API_KEY"
echo "  2. Start infrastructure: docker-compose up -d postgres qdrant redis"
echo "  3. Run the API: uvicorn aerumentis.main:app --reload"
echo "  4. Open http://localhost:8000/docs"
echo ""
echo "  Or start everything with Docker:"
echo "  docker-compose up --build"
echo ""
echo "🛫 Aerumentis is ready for takeoff!"
