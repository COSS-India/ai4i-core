#!/usr/bin/env python3
"""
Merge diverse English training data with existing Indian language data and retrain models.
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

def merge_datasets():
    """Merge diverse English data with existing Indian language data."""
    print("=" * 80)
    print("MERGING TRAINING DATASETS")
    print("=" * 80)
    
    # Load diverse English/Hindi/Bengali data
    diverse_path = Path("data/processed/diverse_training_data.csv")
    if not diverse_path.exists():
        print(f"❌ Error: {diverse_path} not found")
        return None
    
    diverse_df = pd.read_csv(diverse_path)
    print(f"\n✓ Loaded diverse data: {len(diverse_df)} samples")
    print(f"  Languages: {diverse_df['language'].unique()}")
    print(f"  Domains: {diverse_df['domain'].unique()}")
    
    # Load existing Indian language data
    indian_path = Path("data/processed/indian_languages_dataset.csv")
    if not indian_path.exists():
        print(f"❌ Error: {indian_path} not found")
        return None
    
    indian_df = pd.read_csv(indian_path)
    print(f"\n✓ Loaded Indian language data: {len(indian_df)} samples")
    
    # Remove duplicate/repetitive synthetic data from Indian dataset
    # Keep only unique texts (remove the numbered duplicates)
    print("\n📊 Removing repetitive synthetic data...")
    original_count = len(indian_df)
    
    # Remove rows where text ends with a number pattern like " 1", " 2", etc.
    indian_df['text_clean'] = indian_df['text'].str.replace(r'\s+\d+$', '', regex=True)
    indian_df_dedup = indian_df.drop_duplicates(subset=['text_clean', 'domain', 'language'])
    indian_df_dedup = indian_df_dedup.drop(columns=['text_clean'])
    
    removed_count = original_count - len(indian_df_dedup)
    print(f"  Removed {removed_count} duplicate samples")
    print(f"  Kept {len(indian_df_dedup)} unique samples")
    
    # Merge datasets
    merged_df = pd.concat([diverse_df, indian_df_dedup], ignore_index=True)
    print(f"\n✓ Merged dataset: {len(merged_df)} total samples")
    
    # Show distribution
    print("\n📊 Final Distribution:")
    print("\nBy Domain:")
    print(merged_df['domain'].value_counts().sort_index())
    print("\nBy Language:")
    print(merged_df['language'].value_counts().sort_index())
    print("\nBy Domain × Language:")
    dist = merged_df.groupby(['domain', 'language']).size().unstack(fill_value=0)
    print(dist)
    
    # Save merged dataset
    output_path = Path("data/processed/merged_training_data.csv")
    merged_df.to_csv(output_path, index=False)
    print(f"\n✓ Saved merged dataset to: {output_path}")
    
    # Also backup and replace the original dataset
    backup_path = Path("data/processed/indian_languages_dataset_backup.csv")
    indian_df.to_csv(backup_path, index=False)
    print(f"✓ Backed up original to: {backup_path}")
    
    merged_df.to_csv(indian_path, index=False)
    print(f"✓ Replaced {indian_path} with merged data")
    
    return merged_df


def retrain_models():
    """Retrain models using the train_indian_models.py script."""
    print("\n" + "=" * 80)
    print("RETRAINING MODELS")
    print("=" * 80)
    
    import subprocess
    result = subprocess.run(
        ["python3", "scripts/train_indian_models.py"],
        capture_output=True,
        text=True
    )
    
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr)
    
    if result.returncode == 0:
        print("\n✓ Models retrained successfully!")
        return True
    else:
        print(f"\n❌ Model training failed with code {result.returncode}")
        return False


if __name__ == "__main__":
    # Step 1: Merge datasets
    merged_df = merge_datasets()
    
    if merged_df is None:
        print("\n❌ Failed to merge datasets")
        sys.exit(1)
    
    # Step 2: Retrain models
    print("\n" + "=" * 80)
    print("Starting model retraining...")
    print("=" * 80)
    
    success = retrain_models()
    
    if success:
        print("\n" + "=" * 80)
        print("✅ COMPLETE: Datasets merged and models retrained!")
        print("=" * 80)
        print("\nNext steps:")
        print("1. Restart the API server")
        print("2. Run diagnostic tests: python3 scripts/diagnose_classification_issues.py")
        print("3. Verify English text classification is working correctly")
    else:
        print("\n❌ Failed to retrain models")
        sys.exit(1)

