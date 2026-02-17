"""Training pipeline for domain classifier and complexity regressor."""
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

# Add parent directory to path to import features module
sys.path.insert(0, str(Path(__file__).parent.parent))
from request_profiler.features import extract_numeric_features, FEATURE_NAMES

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def train_domain_classifier(
    texts: list,
    labels: list,
    output_path: Path = Path("models/domain_pipeline.pkl"),
) -> dict:
    """Train TF-IDF + Logistic Regression domain classifier.
    
    Args:
        texts: List of text samples
        labels: List of domain labels
        output_path: Path to save the trained model
        
    Returns:
        Dictionary of training metrics
    """
    logger.info("Training domain classifier...")
    
    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=5000,
            ngram_range=(1, 2),
            sublinear_tf=True,
            min_df=2,
            strip_accents="unicode",
        )),
        ("clf", LogisticRegression(
            C=1.0,
            solver="lbfgs",
            max_iter=1000,
            class_weight="balanced",
            multi_class="multinomial",
            random_state=42,
        )),
    ])

    # 5-fold stratified CV
    logger.info("  Running 5-fold cross-validation...")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_scores = cross_val_score(pipeline, texts, labels, cv=cv, scoring="f1_macro")
    
    logger.info(f"  CV F1-macro: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")

    # Final fit on all training data
    logger.info("  Fitting final model on all training data...")
    pipeline.fit(texts, labels)
    
    # Save model
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, output_path)
    logger.info(f"  Model saved to: {output_path}")

    # Evaluate on training data (for reference)
    y_pred = pipeline.predict(texts)
    train_accuracy = accuracy_score(labels, y_pred)
    train_f1 = f1_score(labels, y_pred, average="macro")

    metrics = {
        "cv_f1_macro_mean": float(np.mean(cv_scores)),
        "cv_f1_macro_std": float(np.std(cv_scores)),
        "train_accuracy": float(train_accuracy),
        "train_f1_macro": float(train_f1),
        "n_samples": len(texts),
        "n_classes": len(set(labels)),
    }
    
    logger.info(f"  Training metrics: {metrics}")
    return metrics


def train_complexity_regressor(
    texts: list,
    scores: list,
    output_path: Path = Path("models/complexity_regressor.pkl"),
) -> dict:
    """Train RandomForestRegressor for complexity scoring.
    
    Args:
        texts: List of text samples
        scores: List of complexity scores (0.0-1.0)
        output_path: Path to save the trained model
        
    Returns:
        Dictionary of training metrics
    """
    logger.info("Training complexity regressor...")
    
    # Extract numeric features
    logger.info("  Extracting features for complexity model...")
    X = np.array([extract_numeric_features(t) for t in texts])
    y = np.array(scores)
    
    logger.info(f"  Feature matrix shape: {X.shape}")
    logger.info(f"  Target shape: {y.shape}")

    # Train RandomForest
    logger.info("  Training RandomForestRegressor...")
    rf = RandomForestRegressor(
        n_estimators=300,
        max_depth=15,
        min_samples_leaf=5,
        max_features="sqrt",
        n_jobs=-1,
        random_state=42,
    )
    
    rf.fit(X, y)
    
    # Save model
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(rf, output_path)
    logger.info(f"  Model saved to: {output_path}")
    
    # Save feature names
    feature_path = output_path.parent / "complexity_regressor_features.pkl"
    joblib.dump(FEATURE_NAMES, feature_path)
    logger.info(f"  Feature names saved to: {feature_path}")

    # Evaluate
    y_pred = rf.predict(X)
    rmse = np.sqrt(mean_squared_error(y, y_pred))
    mae = mean_absolute_error(y, y_pred)
    r2 = r2_score(y, y_pred)

    metrics = {
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2),
        "n_samples": len(texts),
        "n_features": X.shape[1],
    }
    
    logger.info(f"  Training metrics: {metrics}")
    
    # Feature importance
    feature_importance = sorted(
        zip(FEATURE_NAMES, rf.feature_importances_),
        key=lambda x: x[1],
        reverse=True
    )
    logger.info("  Top 5 feature importances:")
    for name, importance in feature_importance[:5]:
        logger.info(f"    {name}: {importance:.4f}")

    return metrics


def main():
    """Main training pipeline."""
    logger.info("=" * 70)
    logger.info("Translation Request Profiler - Model Training")
    logger.info("=" * 70)

    # Load dataset
    dataset_path = Path("data/processed/profiler_dataset.csv")
    if not dataset_path.exists():
        logger.error(f"Dataset not found: {dataset_path}")
        logger.error("Please run scripts/collect_data.py first")
        return

    logger.info(f"Loading dataset from: {dataset_path}")
    df = pd.read_csv(dataset_path)

    # Filter to training set only
    train_df = df[df["split"] == "train"].copy()
    logger.info(f"Training samples: {len(train_df)}")
    logger.info(f"Domain distribution:\n{train_df['domain'].value_counts()}")

    # Train domain classifier
    logger.info("")
    domain_metrics = train_domain_classifier(
        texts=train_df["text"].tolist(),
        labels=train_df["domain"].tolist(),
    )

    # Train complexity regressor
    logger.info("")
    complexity_metrics = train_complexity_regressor(
        texts=train_df["text"].tolist(),
        scores=train_df["complexity_score"].tolist(),
    )

    # Save model metadata
    logger.info("")
    logger.info("Saving model metadata...")
    metadata = {
        "version": "1.0.0",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "dataset_version": "v1_18k",
        "dataset_path": str(dataset_path),
        "models": {
            "domain_classifier": {
                "type": "sklearn.pipeline.Pipeline",
                "file": "domain_pipeline.pkl",
                "metrics": domain_metrics,
            },
            "complexity_regressor": {
                "type": "sklearn.ensemble.RandomForestRegressor",
                "file": "complexity_regressor.pkl",
                "metrics": complexity_metrics,
            },
        },
        "feature_count": len(FEATURE_NAMES),
        "feature_names": FEATURE_NAMES,
    }

    metadata_path = Path("models/model_metadata.json")
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info(f"Metadata saved to: {metadata_path}")

    # Evaluate on test set
    logger.info("")
    logger.info("=" * 70)
    logger.info("Evaluating on test set...")
    logger.info("=" * 70)

    test_df = df[df["split"] == "test"].copy()
    logger.info(f"Test samples: {len(test_df)}")

    # Load trained models
    domain_model = joblib.load("models/domain_pipeline.pkl")
    complexity_model = joblib.load("models/complexity_regressor.pkl")

    # Evaluate domain classifier
    logger.info("")
    logger.info("Domain Classifier Test Results:")
    y_true_domain = test_df["domain"].tolist()
    y_pred_domain = domain_model.predict(test_df["text"].tolist())

    test_accuracy = accuracy_score(y_true_domain, y_pred_domain)
    test_f1 = f1_score(y_true_domain, y_pred_domain, average="macro")

    logger.info(f"  Accuracy: {test_accuracy:.4f}")
    logger.info(f"  F1-macro: {test_f1:.4f}")
    logger.info("")
    logger.info("Classification Report:")
    print(classification_report(y_true_domain, y_pred_domain))

    # Evaluate complexity regressor
    logger.info("")
    logger.info("Complexity Regressor Test Results:")
    y_true_complexity = test_df["complexity_score"].tolist()
    X_test = np.array([extract_numeric_features(t) for t in test_df["text"].tolist()])
    y_pred_complexity = complexity_model.predict(X_test)

    test_rmse = np.sqrt(mean_squared_error(y_true_complexity, y_pred_complexity))
    test_mae = mean_absolute_error(y_true_complexity, y_pred_complexity)
    test_r2 = r2_score(y_true_complexity, y_pred_complexity)

    logger.info(f"  RMSE: {test_rmse:.4f}")
    logger.info(f"  MAE: {test_mae:.4f}")
    logger.info(f"  R²: {test_r2:.4f}")

    # Update metadata with test metrics
    metadata["models"]["domain_classifier"]["test_metrics"] = {
        "accuracy": float(test_accuracy),
        "f1_macro": float(test_f1),
    }
    metadata["models"]["complexity_regressor"]["test_metrics"] = {
        "rmse": float(test_rmse),
        "mae": float(test_mae),
        "r2": float(test_r2),
    }

    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    logger.info("")
    logger.info("=" * 70)
    logger.info("Training Complete!")
    logger.info("=" * 70)
    logger.info(f"Models saved in: models/")
    logger.info(f"Metadata: {metadata_path}")
    logger.info("")


if __name__ == "__main__":
    main()

