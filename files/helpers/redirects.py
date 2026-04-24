from files.helpers.config.environment import SITE_FULL


def same_site_relative_url(url):
	if not url:
		return None

	url = url.strip()

	if url.startswith('/'):
		return url

	if url == SITE_FULL:
		return '/'

	site_prefix = f'{SITE_FULL}/'
	if url.startswith(site_prefix):
		return '/' + url.removeprefix(site_prefix)

	return None
