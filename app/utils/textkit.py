"""Text processing helpers."""


def split_keywords(text):
    """Split a keyword string by newline or comma into a list of trimmed tokens.

    Returns an empty list for None / empty / whitespace-only input.
    """
    if not text or not text.strip():
        return []
    # Split on newlines first, then commas within each chunk
    tokens = []
    for chunk in text.replace('\r', '').split('\n'):
        for part in chunk.split(','):
            t = part.strip()
            if t:
                tokens.append(t)
    return tokens
