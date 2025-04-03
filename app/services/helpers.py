import hashlib


def generate_hash(doc: str) -> str:
    """
    Generate a unique hash based on the document content and URL.
    """
    hash_input = doc.encode('utf-8')
    return hashlib.md5(hash_input).hexdigest()
