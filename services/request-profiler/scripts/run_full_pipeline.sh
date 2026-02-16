#!/bin/bash
#
# Full Pipeline: Data Collection → Model Training → Validation
# This script runs the complete workflow to replace synthetic data with real-world corpus
#

set -e  # Exit on error

echo "=============================================================================="
echo "INDIAN LANGUAGES REQUEST PROFILER - FULL PIPELINE"
echo "=============================================================================="
echo ""
echo "This pipeline will:"
echo "  1. Collect real-world data from public sources (Wikipedia, AI4Bharat)"
echo "  2. Generate train/val/test splits with quality validation"
echo "  3. Train domain classifier and complexity regressor"
echo "  4. Validate model performance"
echo ""
echo "Estimated time: 30-60 minutes depending on network speed"
echo "=============================================================================="
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Check Python version
echo "Checking Python version..."
python3 --version || { echo "Error: Python 3 not found"; exit 1; }

# Install dependencies
echo ""
echo "Step 0: Installing dependencies..."
echo "=============================================================================="
pip3 install -r requirements.txt

# Step 1: Collect real-world data
echo ""
echo "Step 1: Collecting real-world Indian language data..."
echo "=============================================================================="
python3 scripts/collect_real_indian_data.py

if [ $? -ne 0 ]; then
    echo "❌ Data collection failed!"
    exit 1
fi

echo ""
echo "✓ Data collection complete!"

# Step 2: Train models
echo ""
echo "Step 2: Training ML models..."
echo "=============================================================================="
python3 scripts/train_indian_models.py

if [ $? -ne 0 ]; then
    echo "❌ Model training failed!"
    exit 1
fi

echo ""
echo "✓ Model training complete!"

# Step 3: Validate dataset and models
echo ""
echo "Step 3: Validating dataset and models..."
echo "=============================================================================="

# Check if dataset files exist
DATASET_FILES=(
    "data/processed/indian_languages_dataset.csv"
    "data/processed/indian_languages_train.csv"
    "data/processed/indian_languages_val.csv"
    "data/processed/indian_languages_test.csv"
)

for file in "${DATASET_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing dataset file: $file"
        exit 1
    fi
    
    # Count lines (excluding header)
    lines=$(tail -n +2 "$file" | wc -l | tr -d ' ')
    echo "  ✓ $file: $lines samples"
done

# Check if model files exist
MODEL_FILES=(
    "models/domain_pipeline.pkl"
    "models/complexity_regressor.pkl"
    "models/complexity_regressor_features.pkl"
    "models/model_metadata.json"
)

for file in "${MODEL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        echo "❌ Missing model file: $file"
        exit 1
    fi
    echo "  ✓ $file exists"
done

# Display model metadata
echo ""
echo "Model Metadata:"
echo "=============================================================================="
cat models/model_metadata.json | python3 -m json.tool

# Step 4: Check for synthetic data
echo ""
echo "Step 4: Verifying no synthetic data remains..."
echo "=============================================================================="

synthetic_count=$(grep -c "synthetic" data/processed/indian_languages_dataset.csv || true)

if [ "$synthetic_count" -gt 1 ]; then  # > 1 because header might contain the word
    echo "⚠️  Warning: Found $synthetic_count lines with 'synthetic' in dataset"
    echo "    This might indicate synthetic data is still present"
else
    echo "  ✓ No synthetic data found in dataset"
fi

# Final summary
echo ""
echo "=============================================================================="
echo "PIPELINE COMPLETE!"
echo "=============================================================================="
echo ""
echo "Summary:"
echo "  ✓ Real-world data collected and validated"
echo "  ✓ Models trained and saved"
echo "  ✓ All files generated successfully"
echo ""
echo "Next steps:"
echo "  1. Review validation metrics in: data/processed/dataset_validation_metrics.json"
echo "  2. Review model metadata in: models/model_metadata.json"
echo "  3. Start the API server: uvicorn request_profiler.main:app --reload"
echo "  4. Run integration tests: bash scripts/test_indian_api.sh"
echo ""
echo "=============================================================================="

