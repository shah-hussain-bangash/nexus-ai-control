"""Shared search-only Arabic normalization. Stored text and citation hashes stay original."""
import re
import unicodedata

NORMALIZATION_VERSION = 'arabic-search-v1'
LETTERS = str.maketrans({'أ':'ا', 'إ':'ا', 'آ':'ا', 'ٱ':'ا', 'ى':'ي', 'ی':'ي', 'ک':'ك'})


def arabic_mark(char):
    return unicodedata.category(char) in ('Mn', 'Me') and 'ARABIC' in unicodedata.name(char, '')


def normalized_text(value):
    expanded = []
    for char in unicodedata.normalize('NFC', value):
        if '\ufb50' <= char <= '\ufdff' or '\ufe70' <= char <= '\ufeff':
            compatible = unicodedata.normalize('NFKC', char)
            # Isolated presentation-form vowel marks may decompose with a space.
            if all(c in (' ', '\u0640') or arabic_mark(c) for c in compatible): continue
            expanded.append(compatible)
        else:
            expanded.append(char)
    folded = unicodedata.normalize('NFC', ''.join(expanded)).translate(LETTERS)
    return ''.join(c for c in folded if c != '\u0640' and not arabic_mark(c)).casefold()


def search_tokens(value):
    return re.findall(r'\w+', normalized_text(value))
