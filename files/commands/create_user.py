import click

from files.__main__ import app, db_session
from files.classes import User
from files.helpers.config.regex import email_regex, valid_password_regex, valid_username_regex


def create_user_worker(username: str, email: str | None, password: str) -> User:
	username = username.strip()
	email = email.strip().lower() if email else None

	if not valid_username_regex.fullmatch(username):
		raise ValueError("Invalid username")

	if not valid_password_regex.fullmatch(password):
		raise ValueError("Password must be between 8 and 100 characters.")

	if email and not email_regex.fullmatch(email):
		raise ValueError("Invalid email.")

	db = db_session()

	existing_username = db.query(User.id).filter_by(username=username).first()
	if existing_username:
		raise ValueError("An account with that username already exists.")

	if email:
		existing_email = db.query(User.id).filter_by(email=email).first()
		if existing_email:
			raise ValueError("An account with that email already exists.")

	user = User(
		username=username,
		original_username=username,
		admin_level=0,
		password=password,
		email=email,
		ban_evade=0,
		profileurl="/assets/images/default-profile-pic.webp",
	)
	db.add(user)
	db.commit()
	db.refresh(user)

	return user


@app.cli.command("create_user")
@click.argument("username")
@click.argument("email")
@click.argument("password")
def create_user(username: str, email: str, password: str):
	user = create_user_worker(username, email, password)
	click.echo(f"Created user: {user.username} (id: {user.id})")
