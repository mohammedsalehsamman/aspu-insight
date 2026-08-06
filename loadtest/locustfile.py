import random

from locust import HttpUser, task, between, constant_pacing

from tests_common.files import make_valid_pdf_bytes

LOGIN_URL = '/api/auth/ASPU-2004/login/'
REFRESH_URL = '/api/auth/ASPU-2004/refresh/'
PAPERS_URL = '/api/research/researchAspu2004/papers/'
SMART_SEARCH_URL = '/api/research/researchAspu2004/papers/smart-search/'
AUTHOR_DASHBOARD_URL = '/api/research/researchAspu2004/author/dashboard/'
AI_KEYWORDS_URL = '/api/ai/ai2004-R/keywords/suggest/'
ADMIN_STATS_URL = '/api/admin/2004-R/dashboard/stats/'
ADMIN_PAPERS_URL = '/api/admin/2004-R/dashboard/papers/'

LOADTEST_PASSWORD = 'LoadTest123!'

SEARCH_TERMS = ['learning', 'network', 'analysis', 'system', 'data', 'model']


def paper_detail_url(paper_id):
    return f'{PAPERS_URL}{paper_id}/'


def paper_download_url(paper_id):
    return f'{PAPERS_URL}{paper_id}/download/'


def paper_plagiarism_url(paper_id):
    return f'{PAPERS_URL}{paper_id}/plagiarism-report/'


def paper_metadata_quality_url(paper_id):
    return f'{PAPERS_URL}{paper_id}/metadata-quality/'


class _LoggedInMixin:

    role_prefix = None
    pool_size = 1

    def on_start(self):
        n = random.randint(1, self.pool_size)
        email = f'loadtest_{self.role_prefix}{n}@example.com'
        response = self.client.post(LOGIN_URL, json={
            'email': email, 'password': LOADTEST_PASSWORD,
        }, name=f'{LOGIN_URL} [{self.role_prefix}]')
        data = response.json() if response.status_code == 200 else {}
        self.access_token = data.get('access')
        self.refresh_token = data.get('refresh')

    def auth_headers(self):
        return {'Authorization': f'Bearer {self.access_token}'} if self.access_token else {}

    @task(1)
    def refresh_access_token(self):
        if not self.refresh_token:
            return
        response = self.client.post(REFRESH_URL, json={
            'refresh': self.refresh_token,
        }, name=f'{REFRESH_URL} [{self.role_prefix}]')
        if response.status_code == 200:
            self.access_token = response.json().get('access')


def _fetch_paper_ids(client, params=None, limit=30):
    response = client.get(PAPERS_URL, params=params, name=f'{PAPERS_URL} [seed ids]')
    if response.status_code != 200:
        return []
    try:
        return [p['id'] for p in response.json()[:limit]]
    except (ValueError, KeyError, TypeError):
        return []


class AnonymousReaderUser(HttpUser):

    weight = 6
    wait_time = between(1, 3)

    def on_start(self):
        self.paper_ids = _fetch_paper_ids(self.client)

    @task(5)
    def list_papers(self):
        self.client.get(PAPERS_URL, name=f'{PAPERS_URL} [list]')

    @task(3)
    def view_paper_detail(self):
        if not self.paper_ids:
            self.paper_ids = _fetch_paper_ids(self.client)
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_detail_url(paper_id), name=f'{PAPERS_URL}<id>/ [detail]')

    @task(2)
    def download_paper(self):
        if not self.paper_ids:
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_download_url(paper_id), name=f'{PAPERS_URL}<id>/download/')

    @task(1)
    def smart_search(self):
        self.client.get(SMART_SEARCH_URL, params={'q': random.choice(SEARCH_TERMS)},
                         name=f'{SMART_SEARCH_URL} [q=...]')


class AuthorUser(_LoggedInMixin, HttpUser):

    role_prefix = 'author'
    pool_size = 5
    weight = 3
    wait_time = between(2, 5)

    def on_start(self):
        super().on_start()
        self.paper_ids = _fetch_paper_ids(self.client, params={'search': ''})

    @task(4)
    def own_dashboard(self):
        self.client.get(AUTHOR_DASHBOARD_URL, headers=self.auth_headers(), name=AUTHOR_DASHBOARD_URL)

    @task(3)
    def view_own_or_any_paper(self):
        if not self.paper_ids:
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_detail_url(paper_id), headers=self.auth_headers(),
                         name=f'{PAPERS_URL}<id>/ [detail, auth]')

    @task(1)
    def create_paper(self):
        files = {'pdf_file': ('loadtest_upload.pdf', make_valid_pdf_bytes(1), 'application/pdf')}
        data = {
            'title': f'Locust submission {random.randint(1, 10**9)}',
            'abstract': 'Generated during a Locust load test run.',
            'specialization': 'computer_science',
        }
        self.client.post(PAPERS_URL, data=data, files=files, headers=self.auth_headers(),
                          name=f'{PAPERS_URL} [create]')


class ReviewerUser(_LoggedInMixin, HttpUser):

    role_prefix = 'reviewer'
    pool_size = 3
    weight = 2
    wait_time = between(2, 5)

    def on_start(self):
        super().on_start()
        self.paper_ids = _fetch_paper_ids(self.client)

    @task(3)
    def list_papers(self):
        self.client.get(PAPERS_URL, headers=self.auth_headers(), name=f'{PAPERS_URL} [list, reviewer]')

    @task(1)
    def view_paper_detail(self):
        if not self.paper_ids:
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_detail_url(paper_id), headers=self.auth_headers(),
                         name=f'{PAPERS_URL}<id>/ [detail, reviewer]')


class EditorUser(_LoggedInMixin, HttpUser):
    role_prefix = 'editor'
    pool_size = 2
    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        super().on_start()
        self.paper_ids = _fetch_paper_ids(self.client)

    @task
    def list_papers(self):
        self.client.get(PAPERS_URL, headers=self.auth_headers(), name=f'{PAPERS_URL} [list, editor]')


class AssistantEditorUser(_LoggedInMixin, HttpUser):

    role_prefix = 'assistant_editor'
    pool_size = 2
    weight = 1
    wait_time = between(2, 5)

    @task
    def list_all_papers(self):
        self.client.get(PAPERS_URL, headers=self.auth_headers(), name=f'{PAPERS_URL} [list, assistant]')


class AdminUser(_LoggedInMixin, HttpUser):
    role_prefix = 'admin'
    pool_size = 1
    weight = 1
    wait_time = between(3, 8)

    @task(2)
    def dashboard_stats(self):
        self.client.get(ADMIN_STATS_URL, headers=self.auth_headers(), name=ADMIN_STATS_URL)

    @task(1)
    def admin_paper_list(self):
        self.client.get(ADMIN_PAPERS_URL, headers=self.auth_headers(), name=ADMIN_PAPERS_URL)


class HeavyMLUser(_LoggedInMixin, HttpUser):

    role_prefix = 'author'
    pool_size = 5
    weight = 1
    wait_time = constant_pacing(5)

    def on_start(self):
        super().on_start()
        self.paper_ids = _fetch_paper_ids(self.client)

    @task(2)
    def plagiarism_report(self):
        if not self.paper_ids:
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_plagiarism_url(paper_id), headers=self.auth_headers(),
                         name=f'{PAPERS_URL}<id>/plagiarism-report/')

    @task(2)
    def metadata_quality_report(self):
        if not self.paper_ids:
            return
        paper_id = random.choice(self.paper_ids)
        self.client.get(paper_metadata_quality_url(paper_id), headers=self.auth_headers(),
                         name=f'{PAPERS_URL}<id>/metadata-quality/')

    @task(1)
    def keyword_suggest(self):
        self.client.post(AI_KEYWORDS_URL, json={
            'text': 'A short abstract about machine learning applications in medical imaging.',
        }, headers=self.auth_headers(), name=AI_KEYWORDS_URL)
