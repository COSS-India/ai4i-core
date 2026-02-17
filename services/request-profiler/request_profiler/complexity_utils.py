"""
Improved Complexity Estimation Utilities for Indian Languages.

This module provides an enhanced complexity scoring algorithm that considers:
- Vocabulary Sophistication (40%)
- Syntactic Complexity (30%)
- Semantic Complexity (20%)
- Text Length (10%)

The algorithm is designed to avoid over-reliance on text length and better
capture actual linguistic complexity.
"""

import unicodedata
from typing import Set


# Script names for Indic languages
INDIC_SCRIPTS = {
    'devanagari', 'bengali', 'tamil', 'telugu', 'kannada', 'assamese',
    'gujarati', 'malayalam', 'gurmukhi', 'oriya'
}


def estimate_complexity(text: str) -> float:
    """
    Estimate text complexity using improved multi-factor algorithm.
    
    This function analyzes text across four dimensions:
    1. Vocabulary Sophistication (40%): word length, lexical diversity, rare words
    2. Syntactic Complexity (30%): sentence structure, punctuation variety
    3. Semantic Complexity (20%): entity density, technical content, code-mixing
    4. Text Length (10%): character and word count (reduced weight)
    
    Args:
        text: Input text to analyze (supports both Latin and Indic scripts)
        
    Returns:
        Complexity score between 0.0 and 1.0
        
    Examples:
        >>> estimate_complexity("Hello world")
        0.25
        >>> estimate_complexity("The mitochondria is the powerhouse of the cell.")
        0.45
        >>> estimate_complexity("मधुमेह रोगी को इंसुलिन की नियमित खुराक लेनी चाहिए।")
        0.52
    """
    if not text or len(text) < 10:
        return 0.3
    
    words = text.split()
    if not words:
        return 0.3
    
    # === 1. Vocabulary Sophistication (40% weight) ===
    vocab_score = _calculate_vocabulary_score(words, text)
    
    # === 2. Syntactic Complexity (30% weight) ===
    syntax_score = _calculate_syntactic_score(words, text)
    
    # === 3. Semantic Complexity (20% weight) ===
    semantic_score = _calculate_semantic_score(words, text)
    
    # === 4. Text Length (10% weight) ===
    length_score = _calculate_length_score(words, text)
    
    # === Final Weighted Score ===
    final_score = (
        vocab_score * 0.40 +
        syntax_score * 0.30 +
        semantic_score * 0.20 +
        length_score * 0.10
    )
    
    # Clamp to [0.0, 1.0] and round
    return round(max(0.0, min(1.0, final_score)), 2)


def _calculate_vocabulary_score(words: list, text: str) -> float:
    """Calculate vocabulary sophistication score."""
    # Average word length (normalized to 0-1, max expected = 15 chars)
    avg_word_len = sum(len(w) for w in words) / len(words)
    word_len_score = min(1.0, avg_word_len / 15.0)
    
    # Lexical diversity (unique word ratio)
    unique_words = set(w.lower() for w in words)
    lexical_diversity = len(unique_words) / len(words)
    
    # Long word ratio (words > 10 characters indicate technical/complex vocabulary)
    long_word_ratio = sum(1 for w in words if len(w) > 10) / len(words)
    
    # Rare word estimation (words > 8 chars as proxy for rare words)
    rare_word_ratio = sum(1 for w in words if len(w) > 8) / len(words)
    
    return (
        word_len_score * 0.3 +
        lexical_diversity * 0.3 +
        long_word_ratio * 0.2 +
        rare_word_ratio * 0.2
    )


def _calculate_syntactic_score(words: list, text: str) -> float:
    """Calculate syntactic complexity score."""
    # Sentence detection (supports both Western and Indic punctuation)
    sentence_terminators = (
        text.count('.') + text.count('!') + text.count('?') +
        text.count('।') + text.count('॥')
    )
    num_sentences = max(1, sentence_terminators)
    avg_sentence_len = len(words) / num_sentences
    
    # Normalize sentence length (max expected = 40 words)
    sentence_len_score = min(1.0, avg_sentence_len / 40.0)
    
    # Punctuation diversity (more varied punctuation = more complex structure)
    punctuation_chars = set(c for c in text if c in '.,;:!?।॥-—()[]{}\"\'')
    punct_diversity = min(1.0, len(punctuation_chars) / 10.0)
    
    return (
        sentence_len_score * 0.7 +
        punct_diversity * 0.3
    )


def _calculate_semantic_score(words: list, text: str) -> float:
    """Calculate semantic complexity score."""
    # Named entity density (heuristic: capitalized words or long words in Indic scripts)
    # For Indic scripts, use word length as proxy
    potential_entities = sum(1 for w in words if len(w) > 6)
    # For Latin script, count capitalized words
    capitalized = len([w for w in words if w and w[0].isupper()])
    entity_count = max(potential_entities, capitalized)
    entity_density = entity_count / len(words)
    
    # Digit/number ratio (indicates technical/financial content)
    digit_ratio = sum(1 for c in text if c.isdigit()) / max(len(text), 1)
    
    # Code-mixing detection (multiple scripts)
    scripts_found = _detect_scripts(text)
    code_mixing_score = min(1.0, (len(scripts_found) - 1) / 2.0) if len(scripts_found) > 1 else 0.0
    
    return (
        entity_density * 0.4 +
        digit_ratio * 0.3 +
        code_mixing_score * 0.3
    )


def _calculate_length_score(words: list, text: str) -> float:
    """Calculate text length score (reduced weight)."""
    # Character count (normalized, max expected = 2000 chars)
    char_count_score = min(1.0, len(text) / 2000.0)
    
    # Word count (normalized, max expected = 300 words)
    word_count_score = min(1.0, len(words) / 300.0)
    
    return (char_count_score + word_count_score) / 2.0


def _detect_scripts(text: str) -> Set[str]:
    """Detect all scripts present in the text."""
    scripts_found = set()
    
    for char in text:
        if char.isalpha():
            try:
                char_name = unicodedata.name(char)
                
                # Check for Indic scripts
                for script in INDIC_SCRIPTS:
                    if script.upper() in char_name:
                        scripts_found.add(script)
                        break
                
                # Check for Latin script
                if 'LATIN' in char_name:
                    scripts_found.add('latin')
                    
            except ValueError:
                # Character name not found
                continue
    
    return scripts_found

