import time
import requests
from difflib import SequenceMatcher
from ai_service.utils.extactor import TextExtractor
from ai_service.utils.ai_keywordExtractor import AIKeywordExtractor

class PlagiarismAnalyzer:
    def init(self, api_key: str, chunk_size=30):
        self.api_key = api_key
        self.extractor = TextExtractor(chunk_size=chunk_size)
        self.ai_extractor = AIKeywordExtractor()

    def _fetch_serp_results(self, keyword_chunk: str, ai_keywords: list) -> list:
        api_url = "https://api.valueserp.com/search"
        context_query = f'"{keyword_chunk}" ' + " ".join(ai_keywords[:2])
        params = {
            'api_key': self.api_key,
            'q': context_query,
            'search_type': 'scholar'
        }
        try:
            response = requests.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json().get('organic_results', [])
        except requests.RequestException:
            pass
        return []

    def calculate_similarity(self, raw_text: str) -> dict:
        ai_keywords = self.ai_extractor.extract_pure_keywords(raw_text, top_n=5)
        chunks = self.extractor.generate_keywords(raw_text)
        detected_sources = {}
        target_chunks = chunks

        if not target_chunks:
            return {"total_score": 0.0, "sources": [], "ai_tags": ai_keywords}

        for chunk in target_chunks:
            results = self._fetch_serp_results(chunk, ai_keywords)
            time.sleep(0.2)
            
            for result in results:
                url = result.get('link')
                title = result.get('title')
                snippet = result.get('snippet', '')
                
                if not url:
                    continue
                
                similarity_ratio = SequenceMatcher(None, chunk, snippet).ratio() * 100
                if similarity_ratio > 40:
                    if url in detected_sources:
                        detected_sources[url]['match_count'] += 1
                    else:
                        detected_sources[url] = {
                            'url': url,
                            'title': title,
                            'snippet': snippet,
                            'match_percentage': round(similarity_ratio, 2),
                            'match_count': 1
                        }

        total_score = (len(detected_sources) / len(target_chunks)) * 100
        return {
            "total_score": min(100.0, round(total_score, 2)),
            "sources": list(detected_sources.values()),
            "ai_tags": ai_keywords
        }