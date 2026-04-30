#!/bin/bash
# Download required models for the Translation Request Profiler

set -e

MODELS_DIR="models"
mkdir -p "$MODELS_DIR"

echo "=== Downloading fastText language identification model ==="
# Try to download the compressed .ftz model first (smaller, faster)
if [ ! -f "$MODELS_DIR/lid.176.ftz" ] && [ ! -f "$MODELS_DIR/lid.176.bin" ]; then
    echo "Downloading lid.176.ftz (compressed, ~917 KB)..."
    curl -L -o "$MODELS_DIR/lid.176.ftz" \
        "https://dl.fbaipublicfiles.com/fasttext/supervised-models/lid.176.ftz"
    echo "✓ Downloaded lid.176.ftz"
else
    echo "✓ fastText model already exists"
fi

echo ""
echo "=== Downloading spaCy English model ==="
# Use python3 if python is not available
PYTHON_CMD="python3"
if command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

if ! $PYTHON_CMD -c "import spacy; spacy.load('en_core_web_sm')" 2>/dev/null; then
    echo "Downloading en_core_web_sm..."
    $PYTHON_CMD -m spacy download en_core_web_sm
    echo "✓ Downloaded en_core_web_sm"
else
    echo "✓ spaCy model already installed"
fi

echo ""
echo "=== Downloading common words list ==="
DATA_DIR="data"
mkdir -p "$DATA_DIR"

if [ ! -f "$DATA_DIR/common_words_10k.txt" ]; then
    echo "Downloading top 10,000 English words..."
    # Using Google's 10k most common words
    curl -L -o "$DATA_DIR/common_words_10k.txt" \
        "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears.txt"
    echo "✓ Downloaded common_words_10k.txt"
else
    echo "✓ Common words list already exists"
fi

echo ""
echo "=== All models downloaded successfully! ==="
echo "Models directory: $MODELS_DIR"
echo "Data directory: $DATA_DIR"
ls -lh "$MODELS_DIR"
ls -lh "$DATA_DIR"

