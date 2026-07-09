import re

class TextExtractor:
<<<<<<< HEAD
    def __init__(self, chunk_size=30):
=======
    def init(self, chunk_size=30):
>>>>>>> 8009729a235f7b93b8bdf2dd63e85d842a3aade5
        self.chunk_size = chunk_size

    def clean_text(self, text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def generate_keywords(self, text: str) -> list:
        cleaned = self.clean_text(text)
        words = cleaned.split()
        keywords = []
        for i in range(0, len(words), self.chunk_size):
            keyword = " ".join(words[i:i + self.chunk_size])
            if keyword:
                keywords.append(keyword)
        return keywords