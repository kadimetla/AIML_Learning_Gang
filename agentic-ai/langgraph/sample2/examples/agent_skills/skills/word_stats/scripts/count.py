def run(text: str) -> str:
    words = len(text.split())
    chars = len(text)
    sentences = sum(text.count(c) for c in ".!?")
    return f"words={words} chars={chars} sentences={sentences}"
