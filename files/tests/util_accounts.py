import secrets
import string
from itertools import count

from . import util

from files.__main__ import app, db_session
from files.classes import User


_USERNAME_COUNTER = count()


def _to_base36(num: int) -> str:
	alphabet = string.digits + string.ascii_lowercase
	result = ""
	while num > 0:
		result = alphabet[num % 36] + result
		num //= 36
	return result or "0"


def _make_unique_suffix() -> str:
	# Counter avoids same-process collisions; random tail keeps repeated runs readable
	# without relying on wall-clock time.
	return f"{_to_base36(next(_USERNAME_COUNTER))}{secrets.token_hex(2)}"


def create_test_client_and_user(name="user"):
	"""Create a test client with a newly registered user account."""
	client = app.test_client()
	suffix = _make_unique_suffix()

	# Validate name parameter length to ensure username fits within username length limit
	from files.helpers.config.regex import USERNAME_LENGTH_MAX
	# Format: t-{name}-{suffix} (3 chars overhead + suffix length)
	max_name_length = USERNAME_LENGTH_MAX - 3 - len(suffix)  # 3 = len("t-") + len("-")
	if len(name) > max_name_length:
		raise ValueError(f"name parameter '{name}' is too long ({len(name)} chars). "
						f"Maximum length is {max_name_length} chars to fit within {USERNAME_LENGTH_MAX} char username limit. "
						f"Current unique suffix uses {len(suffix)} chars.")

	username = f"t-{name}-{suffix}"
	print(f"Signing up as {username}")

	signup_post_response, signup_get_response = util.post_with_formkey(
		client, "/signup",
		data={
			"usernametwo": username,
			"password": "password",
			"password_confirm": "password",
			"email": "",
		}
	)

	assert signup_post_response.status_code == 302
	if "error" in signup_post_response.location:
		# Extract and print the error message for debugging
		from urllib.parse import parse_qs, urlparse
		parsed_url = urlparse(signup_post_response.location)
		error_message = parse_qs(parsed_url.query).get('error', ['Unknown error'])[0]
		print(f"Signup failed for user '{username}': {error_message}")
	assert "error" not in signup_post_response.location

	db = db_session
	user = db.query(User).filter_by(username=username).first()

	assert User == type(user)

	return client, user


def create_test_client_and_admin(admin_level, name="admin"):
	"""Create a test client with a newly registered admin user account.

	Args:
		admin_level: Admin level to set (1-3, required)
		name: Base name for the admin user (default: "admin")

	Returns:
		Tuple of (client, admin_user) where admin_user has admin_level set
	"""
	client, user = create_test_client_and_user(name)

	# Set admin level
	user.admin_level = admin_level
	db_session.add(user)
	db_session.commit()

	return client, user


def create_logged_off_client():
	"""Create a test client without authentication."""
	return app.test_client()
