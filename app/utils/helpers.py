"""General-purpose helper functions."""


def format_size(num_bytes):
    """Format a byte count as a human-readable string (B / KB / MB / GB / TB).

    Returns a string with one decimal place, e.g. "1.2 GB".
    """
    if num_bytes is None:
        return '0 B'
    num_bytes = int(num_bytes)
    if num_bytes < 0:
        return '0 B'
    if num_bytes < 1024:
        return f'{num_bytes} B'
    for unit in ('KB', 'MB', 'GB', 'TB'):
        num_bytes /= 1024.0
        if num_bytes < 1024:
            return f'{num_bytes:.1f} {unit}'
    return f'{num_bytes:.1f} PB'


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
