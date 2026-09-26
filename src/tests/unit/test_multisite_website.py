from app.backend.services.info_source.factory import validate_config
from app.backend.services.info_source.website import normalize_url


def test_legacy_config_and_url_normalization():
    validate_config('website', {'url': 'https://example.com/news'})
    assert normalize_url('HTTPS://EXAMPLE.COM/a/?utm_source=x#top') == 'https://example.com/a'


def test_multisite_api_partial_failure(client, admin_headers, sync_worker, monkeypatch):
    from app.backend.services.info_source.website import WebsiteAdapter
    sites = [
        {'name': 'First', 'url': 'https://one.example/news', 'link_selector': 'a.article'},
        {'name': 'Broken', 'url': 'https://broken.example/news'},
        {'name': 'Third', 'url': 'https://three.example/news', 'link_selector': 'a.article'},
    ]
    def fetch(self, url, mode='auto'):
        if 'broken.example' in url:
            raise RuntimeError('listing unavailable')
        if url.endswith('/news'):
            return '<a class="article" href="https://shared.example/story?utm_source=x">Story</a>'
        return '<article>Body</article><title>Story</title>'
    from app.backend.services.info_source.webfetch_client import WebFetchClient
    monkeypatch.setattr(WebFetchClient, 'fetch_html', fetch)
    res = client.post('/api/info-sources', json={'name': 'Combined', 'type': 'website', 'config': {'sites': sites}}, headers=admin_headers)
    assert res.status_code == 201, res.text
    sid = res.json()['id']
    assert client.post(f'/api/info-sources/{sid}/sync', headers=admin_headers).status_code == 200
    source = client.get(f'/api/info-sources/{sid}', headers=admin_headers).json()
    assert source['status'] == 'warning'
    assert source['item_count'] == 1
    assert source['site_status'][sites[1]['url']]['status'] == 'error'
    assert source['site_status'][sites[0]['url']]['item_count'] == 1
    items = client.get(f'/api/info-sources/{sid}/items', headers=admin_headers).json()
    assert len(items) == 1
    assert items[0]['site_name'] == 'First'
    assert items[0]['site_url'] == sites[0]['url']
    assert client.get(f'/api/info-sources/{sid}/items', params={'site_url': sites[2]['url']}, headers=admin_headers).json() == []


def test_legacy_source_api(client, admin_headers, sync_worker, monkeypatch):
    from app.backend.services.info_source.webfetch_client import WebFetchClient
    def fetch(self, url, mode='auto'):
        if url.endswith('/news'):
            return '<a href="/news/story">Story</a>'
        return '<article>Legacy body</article><title>Legacy</title>'
    monkeypatch.setattr(WebFetchClient, 'fetch_html', fetch)
    res = client.post('/api/info-sources', json={'name': 'Old', 'type': 'website', 'config': {'url': 'https://legacy.example/news'}}, headers=admin_headers)
    assert res.status_code == 201
    sid = res.json()['id']
    client.post(f'/api/info-sources/{sid}/sync', headers=admin_headers)
    source = client.get(f'/api/info-sources/{sid}', headers=admin_headers).json()
    assert source['item_count'] == 1
    assert source['site_status']['https://legacy.example/news']['status'] == 'ok'
