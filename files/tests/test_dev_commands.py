from files.__main__ import db_session
from files.classes import Comment, Submission, User
from files.commands.create_user import create_user_worker
from files.commands.generate_data import cleanup_generated_data_worker, generate_data_worker


def test_create_user_worker():
	db_session.query(User).filter_by(username="devcmd_user").delete()
	db_session.commit()

	user = create_user_worker("devcmd_user", "devcmd_user@example.com", "password123")

	assert user.id is not None
	assert user.username == "devcmd_user"
	assert user.email == "devcmd_user@example.com"

	db_session.query(User).filter_by(id=user.id).delete()
	db_session.commit()


def test_generate_data_worker_and_cleanup():
	prefix = "devcmd"
	results = generate_data_worker(
		seed=7,
		users=3,
		submissions=2,
		comments=6,
		max_depth=3,
		batch_size=2,
		clean=True,
		prefix=prefix,
	)

	assert results["created_users"] == 3
	assert results["created_submissions"] == 2
	assert results["created_comments"] == 6

	assert db_session.query(User.id).filter(User.username.like(f"{prefix}_u_%")).count() == 3
	assert db_session.query(Submission.id).filter(Submission.body.like(f"[{prefix}]%")).count() == 2
	assert db_session.query(Comment.id).filter(Comment.body.like(f"[{prefix}]%")).count() == 6

	cleanup_generated_data_worker(prefix=prefix)

	assert db_session.query(User.id).filter(User.username.like(f"{prefix}_u_%")).count() == 0
	assert db_session.query(Submission.id).filter(Submission.body.like(f"[{prefix}]%")).count() == 0
	assert db_session.query(Comment.id).filter(Comment.body.like(f"[{prefix}]%")).count() == 0
