#!/usr/bin/env python3
"""
Training pipeline for Indian Languages models.
Trains domain classifier and complexity regressor on Indian language dataset.
"""
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.pipeline import Pipeline

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import features module
try:
    from request_profiler.features import extract_numeric_features, FEATURE_NAMES
except ModuleNotFoundError:
    # Try alternative import
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from request_profiler.request_profiler.features import extract_numeric_features, FEATURE_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Paths
DATA_DIR = Path(__file__).parent.parent / 'data' / 'processed'
MODELS_DIR = Path(__file__).parent.parent / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_data():
    """Load Indian languages dataset."""
    logger.info("Loading Indian languages dataset...")

    train_df = pd.read_csv(DATA_DIR / 'indian_languages_train.csv')
    val_df = pd.read_csv(DATA_DIR / 'indian_languages_val.csv')
    test_df = pd.read_csv(DATA_DIR / 'indian_languages_test.csv')

    logger.info(f"  Train: {len(train_df)} samples")
    logger.info(f"  Val:   {len(val_df)} samples")
    logger.info(f"  Test:  {len(test_df)} samples")

    return train_df, val_df, test_df


def train_domain_classifier(train_df, test_df):
    """Train domain classifier on Indian language data."""
    logger.info("\n" + "="*80)
    logger.info("TRAINING DOMAIN CLASSIFIER")
    logger.info("="*80)

    X_train = train_df['text'].tolist()
    y_train = train_df['domain'].tolist()
    X_test = test_df['text'].tolist()
    y_test = test_df['domain'].tolist()

    # Create pipeline with TF-IDF + Logistic Regression
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=3000,  # Reduced for speed
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            strip_accents="unicode",
        )),
        ("clf", LogisticRegression(
            C=1.0,
            solver="lbfgs",
            max_iter=500,  # Reduced for speed
            class_weight="balanced",
            multi_class="multinomial",
            random_state=42,
        )),
    ])

    # Train
    logger.info("Training domain classifier...")
    pipeline.fit(X_train, y_train)

    # Evaluate
    y_pred = pipeline.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    f1_macro = f1_score(y_test, y_pred, average='macro')

    logger.info(f"✓ Test Accuracy: {accuracy:.4f}")
    logger.info(f"✓ Test F1-macro: {f1_macro:.4f}")
    logger.info("\nClassification Report:")
    logger.info("\n" + classification_report(y_test, y_pred))

    # Save model
    model_path = MODELS_DIR / 'domain_pipeline.pkl'
    joblib.dump(pipeline, model_path)
    logger.info(f"✓ Saved model to: {model_path}")

    return {
        'accuracy': float(accuracy),
        'f1_macro': float(f1_macro),
        'model_path': str(model_path)
    }


def train_complexity_regressor(train_df, test_df):
    """Train complexity regressor on Indian language data."""
    logger.info("\n" + "="*80)
    logger.info("TRAINING COMPLEXITY REGRESSOR")
    logger.info("="*80)

    # Extract features
    logger.info("Extracting features from training data...")
    X_train = np.array([extract_numeric_features(text) for text in train_df['text']])
    y_train = train_df['complexity'].values

    logger.info("Extracting features from test data...")
    X_test = np.array([extract_numeric_features(text) for text in test_df['text']])
    y_test = test_df['complexity'].values

    # Train Random Forest Regressor
    logger.info("Training Random Forest Regressor...")
    model = RandomForestRegressor(
        n_estimators=50,  # Reduced for speed
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)

    # Evaluate
    y_pred = model.predict(X_test)
    r2 = r2_score(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))

    logger.info(f"✓ Test R²: {r2:.4f}")
    logger.info(f"✓ Test MAE: {mae:.4f}")
    logger.info(f"✓ Test RMSE: {rmse:.4f}")


    # Save model
    model_path = MODELS_DIR / 'complexity_regressor.pkl'
    joblib.dump(model, model_path)
    logger.info(f"✓ Saved model to: {model_path}")

    # Save feature names
    feature_names_path = MODELS_DIR / 'complexity_regressor_features.pkl'
    joblib.dump(FEATURE_NAMES, feature_names_path)
    logger.info(f"✓ Saved feature names to: {feature_names_path}")

    return {
        'r2': float(r2),
        'mae': float(mae),
        'rmse': float(rmse),
        'model_path': str(model_path)
    }


def save_metadata(domain_metrics, complexity_metrics, train_df):
    """Save model metadata."""
    metadata = {
        'model_version': '2.0.0-indian-languages',
        'training_date': datetime.now(timezone.utc).isoformat(),
        'dataset': {
            'name': 'indian_languages_dataset',
            'total_samples': len(train_df),
            'languages': ['hi', 'bn', 'ta', 'te', 'kn', 'as'],
            'domains': ['medical', 'legal', 'technical', 'finance', 'casual', 'general'],
            'source': 'synthetic_indian_languages'
        },
        'domain_classifier': {
            'model_type': 'TfidfVectorizer + LogisticRegression',
            'test_accuracy': domain_metrics['accuracy'],
            'test_f1_macro': domain_metrics['f1_macro'],
            'classes': ['medical', 'legal', 'technical', 'finance', 'casual', 'general']
        },
        'complexity_regressor': {
            'model_type': 'RandomForestRegressor',
            'test_r2': complexity_metrics['r2'],
            'test_mae': complexity_metrics['mae'],
            'test_rmse': complexity_metrics['rmse'],
            'features': FEATURE_NAMES
        }
    }

    metadata_path = MODELS_DIR / 'model_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"\n✓ Saved metadata to: {metadata_path}")
    return metadata


def main():
    """Main training pipeline."""
    logger.info("="*80)
    logger.info("INDIAN LANGUAGES MODEL TRAINING")
    logger.info("="*80)

    try:
        # Load data
        train_df, val_df, test_df = load_data()

        # Train domain classifier
        domain_metrics = train_domain_classifier(train_df, test_df)

        # Train complexity regressor
        complexity_metrics = train_complexity_regressor(train_df, test_df)

        # Save metadata
        metadata = save_metadata(domain_metrics, complexity_metrics, train_df)

        # Print summary
        logger.info("\n" + "="*80)
        logger.info("TRAINING COMPLETE")
        logger.info("="*80)
        logger.info(f"Domain Classifier Accuracy: {domain_metrics['accuracy']:.4f}")
        logger.info(f"Domain Classifier F1-macro: {domain_metrics['f1_macro']:.4f}")
        logger.info(f"Complexity Regressor R²: {complexity_metrics['r2']:.4f}")
        logger.info(f"Complexity Regressor MAE: {complexity_metrics['mae']:.4f}")
        logger.info(f"\nModels saved to: {MODELS_DIR}")

        return True

    except Exception as e:
        logger.error(f"Error during training: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

