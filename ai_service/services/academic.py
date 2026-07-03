import requests

class AcademicSearchService:
    @staticmethod
    def search_sources(keywords):
        
        base_url = "https://api.semanticscholar.org/graph/v1/paper/search"
        
        query = " ".join(keywords[:5]) if keywords else "academic research"
        params = {
            "query": query, 
            "limit": 3, 
            "fields": "title,url,abstract"
        }
        try:
            response = requests.get(base_url, params=params, timeout=5)
            if response.status_code == 200:
                data = response.json().get('data', [])
                results = []
                for p in data:
                    results.append({
                        "title": p.get('title', 'Unknown'),
                        "url": p.get('url', ''),
                        "match_percentage": 75 
                    })
                return results
        except Exception as e:
            print(f"Academic Search Error: {e}")
            return []
        return []