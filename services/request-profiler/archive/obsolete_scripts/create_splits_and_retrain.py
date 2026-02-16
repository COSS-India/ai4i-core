#!/usr/bin/env python3
"""
Create train/val/test splits from merged dataset and retrain models.
"""
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split
import subprocess
import sys

def create_splits():
    """Create train/val/test splits from the merged dataset."""
    print("=" * 80)
    print("CREATING TRAIN/VAL/TEST SPLITS FROM MERGED DATASET")
    print("=" * 80)
    print()
    
    # Load merged dataset
    dataset_path = Path("data/processed/indian_languages_dataset.csv")
    if not dataset_path.exists():
        print(f"❌ Error: {dataset_path} not found")
        return False
    
    df = pd.read_csv(dataset_path)
    print(f"✓ Loaded merged dataset: {len(df)} samples")
    print(f"  Languages: {df['language'].unique()}")
    print(f"  Domains: {df['domain'].unique()}")
    print()
    
    # Show distribution
    print("Distribution by language:")
    print(df['language'].value_counts().sort_index())
    print()
    
    print("Distribution by domain:")
    print(df['domain'].value_counts().sort_index())
    print()
    
    # Create stratified splits (70/15/15)
    # Only stratify by domain (not language) since some languages have very few samples

    # First split: 70% train, 30% temp
    train_df, temp_df = train_test_split(
        df,
        test_size=0.3,
        random_state=42,
        stratify=df['domain']
    )

    # Second split: split temp into 50/50 for val and test (15% each of total)
    val_df, test_df = train_test_split(
        temp_df,
        test_size=0.5,
        random_state=42,
        stratify=temp_df['domain']
    )
    
    print(f"✓ Created splits:")
    print(f"  Train: {len(train_df)} samples ({len(train_df)/len(df)*100:.1f}%)")
    print(f"  Val:   {len(val_df)} samples ({len(val_df)/len(df)*100:.1f}%)")
    print(f"  Test:  {len(test_df)} samples ({len(test_df)/len(df)*100:.1f}%)")
    print()
    
    # Verify English samples are in all splits
    print("English samples per split:")
    print(f"  Train: {len(train_df[train_df['language'] == 'en'])} samples")
    print(f"  Val:   {len(val_df[val_df['language'] == 'en'])} samples")
    print(f"  Test:  {len(test_df[test_df['language'] == 'en'])} samples")
    print()
    
    # Save splits
    train_path = Path("data/processed/indian_languages_train.csv")
    val_path = Path("data/processed/indian_languages_val.csv")
    test_path = Path("data/processed/indian_languages_test.csv")
    
    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)
    
    print(f"✓ Saved splits:")
    print(f"  {train_path}")
    print(f"  {val_path}")
    print(f"  {test_path}")
    print()
    
    return True


def retrain_models():
    """Retrain models using the new splits."""
    print("=" * 80)
    print("RETRAINING MODELS WITH NEW SPLITS")
    print("=" * 80)
    print()
    
    result = subprocess.run(
        ["python3", "scripts/train_indian_models.py"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        # Filter out INFO logs from stderr
        stderr_lines = [line for line in result.stderr.split('\n') 
                       if 'INFO' not in line and line.strip()]
        if stderr_lines:
            print("STDERR:", '\n'.join(stderr_lines))
    
    if result.returncode == 0:
        print("\n✓ Models retrained successfully!")
        return True
    else:
        print(f"\n❌ Model training failed with code {result.returncode}")
        return False


if __name__ == "__main__":
    # Step 1: Create new splits
    if not create_splits():
        print("\n❌ Failed to create splits")
        sys.exit(1)
    
    # Step 2: Retrain models
    print("\n" + "=" * 80)
    print("Starting model retraining with English data...")
    print("=" * 80)
    print()
    
    if not retrain_models():
        print("\n❌ Failed to retrain models")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("✅ COMPLETE: Splits created and models retrained with English data!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("1. Restart the API server to load new models")
    print("2. Test with: curl -X POST http://localhost:8000/api/v1/profile \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"text\": \"I am having fever and headache\"}'")
    print("3. Run diagnostic tests: python3 scripts/diagnose_classification_issues.py")

