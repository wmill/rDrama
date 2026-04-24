import random

import click
from sqlalchemy import func

from files.__main__ import app, db_session
from files.classes import Comment, CommentVote, Submission, User, Vote
from files.classes.visstate import StateMod
from files.helpers.comments import bulk_recompute_descendant_counts

DEFAULT_PREFIX = "devgen"

TOPIC_WORDS = [
	"moderation",
	"performance",
	"culture",
	"federation",
	"ranking",
	"migration",
	"testing",
	"search",
	"tooling",
	"privacy",
	"caching",
	"governance",
]

COMMENT_OPENERS = [
	"Hot take:",
	"Counterpoint:",
	"Serious question:",
	"I think the real issue is",
	"My experience was that",
	"Nobody is talking about",
	"Small anecdote:",
	"Prediction:",
]

COMMENT_ENDINGS = [
	"and that changes the incentives.",
	"once you account for the edge cases.",
	"which explains most of the disagreement here.",
	"but maybe I am overfitting.",
	"and the defaults are doing a lot of work.",
	"which feels obvious in hindsight.",
	"and I do not think the current policy scales.",
	"so the comments are more interesting than the post.",
]

TITLE_PATTERNS = [
	"{prefix} discussion about {topic}",
	"{prefix} notes on {topic}",
	"{prefix} thread: {topic} in practice",
	"{prefix} test post for {topic}",
	"{prefix} case study on {topic}",
	"{prefix} observations about {topic}",
]


def _make_submission_title(prefix: str, rng: random.Random, index: int) -> str:
	pattern = rng.choice(TITLE_PATTERNS)
	return pattern.format(prefix=prefix, topic=rng.choice(TOPIC_WORDS)).capitalize() + f" #{index + 1}"


def _make_comment_body(prefix: str, rng: random.Random, index: int, depth: int) -> str:
	topic_a = rng.choice(TOPIC_WORDS)
	topic_b = rng.choice(TOPIC_WORDS)
	return (
		f"[{prefix}] {rng.choice(COMMENT_OPENERS)} {topic_a} interacts with {topic_b} "
		f"at depth {depth} in comment {index + 1}, {rng.choice(COMMENT_ENDINGS)}"
	)


def _make_post_body(prefix: str, rng: random.Random, index: int) -> str:
	topic = rng.choice(TOPIC_WORDS)
	return (
		f"[{prefix}] Generated post {index + 1} about {topic}. "
		f"This exists to populate a realistic local development thread."
	)


def cleanup_generated_data_worker(prefix: str = DEFAULT_PREFIX) -> dict[str, int]:
	db = db_session()
	user_prefix = f"{prefix}_u_"
	post_marker = f"[{prefix}]"

	generated_comment_ids = [
		comment_id
		for (comment_id,) in db.query(Comment.id).filter(Comment.body.like(f"{post_marker}%")).all()
	]
	generated_submission_ids = [
		submission_id
		for (submission_id,) in db.query(Submission.id).filter(Submission.body.like(f"{post_marker}%")).all()
	]

	comment_votes_deleted = 0
	post_votes_deleted = 0
	comments_deleted = 0
	submissions_deleted = 0
	users_deleted = 0

	if generated_comment_ids:
		comment_votes_deleted = (
			db.query(CommentVote)
			.filter(CommentVote.comment_id.in_(generated_comment_ids))
			.delete(synchronize_session=False)
		)

		max_level = db.query(func.max(Comment.level)).filter(Comment.id.in_(generated_comment_ids)).scalar() or 0
		for level in range(max_level, 0, -1):
			comments_deleted += (
				db.query(Comment)
				.filter(Comment.id.in_(generated_comment_ids), Comment.level == level)
				.delete(synchronize_session=False)
			)

	if generated_submission_ids:
		post_votes_deleted = (
			db.query(Vote)
			.filter(Vote.submission_id.in_(generated_submission_ids))
			.delete(synchronize_session=False)
		)
		submissions_deleted = (
			db.query(Submission)
			.filter(Submission.id.in_(generated_submission_ids))
			.delete(synchronize_session=False)
		)

	users_deleted = (
		db.query(User)
		.filter(User.username.like(f"{user_prefix}%"))
		.delete(synchronize_session=False)
	)

	db.commit()

	return {
		"users": users_deleted,
		"submissions": submissions_deleted,
		"comments": comments_deleted,
		"post_votes": post_votes_deleted,
		"comment_votes": comment_votes_deleted,
	}


def generate_data_worker(
	seed: int = 12345,
	users: int = 50,
	submissions: int = 10,
	comments: int = 1000,
	max_depth: int = 20,
	batch_size: int = 500,
	clean: bool = False,
	clean_only: bool = False,
	prefix: str = DEFAULT_PREFIX,
) -> dict[str, int]:
	if users < 1:
		raise ValueError("users must be at least 1")
	if submissions < 1 and not clean_only:
		raise ValueError("submissions must be at least 1")
	if comments < 0:
		raise ValueError("comments must be at least 0")
	if max_depth < 1:
		raise ValueError("max_depth must be at least 1")
	if batch_size < 1:
		raise ValueError("batch_size must be at least 1")

	rng = random.Random(seed)
	db = db_session()
	post_marker = f"[{prefix}]"

	cleanup_counts = {"users": 0, "submissions": 0, "comments": 0, "post_votes": 0, "comment_votes": 0}
	if clean or clean_only:
		cleanup_counts = cleanup_generated_data_worker(prefix=prefix)
		if clean_only:
			return {
				**cleanup_counts,
				"created_users": 0,
				"created_submissions": 0,
				"created_comments": 0,
			}

	created_users: list[User] = []
	for index in range(users):
		username = f"{prefix}_u_{index + 1:03d}"
		user = db.query(User).filter_by(username=username).one_or_none()
		if user is None:
			user = User(
				username=username,
				original_username=username,
				admin_level=0,
				password="themotteuser",
				email=f"{username}@example.com",
				ban_evade=0,
				profileurl="/assets/images/default-profile-pic.webp",
			)
			db.add(user)
			db.flush()
		created_users.append(user)

	created_submissions: list[Submission] = []
	for index in range(submissions):
		author = rng.choice(created_users)
		body = _make_post_body(prefix, rng, index)
		post = Submission(
			private=False,
			author_id=author.id,
			over_18=False,
			app_id=None,
			is_bot=False,
			url=None,
			body=body,
			body_html=body,
			embed_url=None,
			title=(title := _make_submission_title(prefix, rng, index)),
			title_html=title,
			ghost=False,
			state_mod=StateMod.VISIBLE,
		)
		post.submit(db)
		created_submissions.append(post)

	db.commit()

	created_comments: list[Comment] = []
	comments_by_submission: dict[int, list[Comment]] = {submission.id: [] for submission in created_submissions}

	for index in range(comments):
		author = rng.choice(created_users)
		parent_submission = rng.choice(created_submissions)
		existing_comments = comments_by_submission[parent_submission.id]
		make_reply = bool(existing_comments) and rng.random() < 0.82

		parent_comment = None
		level = 1
		top_comment_id = None
		if make_reply:
			parent_comment = rng.choice(existing_comments)
			if parent_comment.level >= max_depth:
				reply_candidates = [comment for comment in existing_comments if comment.level < max_depth]
				parent_comment = rng.choice(reply_candidates) if reply_candidates else None
			if parent_comment is not None:
				level = parent_comment.level + 1
				top_comment_id = parent_comment.top_comment_id

		body = _make_comment_body(prefix, rng, index, level)
		comment = Comment(
			author_id=author.id,
			parent_submission=parent_submission.id,
			parent_comment_id=parent_comment.id if parent_comment else None,
			top_comment_id=top_comment_id,
			level=level,
			over_18=False,
			is_bot=False,
			app_id=None,
			body_html=body,
			body=body,
			ghost=False,
			state_mod=StateMod.VISIBLE,
		)
		db.add(comment)
		db.flush()

		if comment.top_comment_id is None:
			comment.top_comment_id = comment.id
			db.add(comment)

		created_comments.append(comment)
		comments_by_submission[parent_submission.id].append(comment)

		if (index + 1) % batch_size == 0:
			db.commit()

	db.commit()

	for submission in created_submissions:
		submission.comment_count = len(comments_by_submission[submission.id])
		db.add(submission)

	for user in created_users:
		user.post_count = db.query(Submission.id).filter_by(
			author_id=user.id,
			state_mod=StateMod.VISIBLE,
			state_user_deleted_utc=None,
		).count()
		user.comment_count = db.query(Comment.id).filter(
			Comment.author_id == user.id,
			Comment.parent_submission != None,
			Comment.state_mod == StateMod.VISIBLE,
			Comment.state_user_deleted_utc == None,
		).count()
		db.add(user)

	db.commit()
	bulk_recompute_descendant_counts(
		predicate=lambda statement: statement.where(Comment.body.like(f"{post_marker}%")),
		db=db,
	)

	return {
		**cleanup_counts,
		"created_users": len(created_users),
		"created_submissions": len(created_submissions),
		"created_comments": len(created_comments),
	}


@app.cli.command("generate_data")
@click.option("--seed", default=12345, show_default=True, type=int)
@click.option("--users", "user_count", default=50, show_default=True, type=int)
@click.option("--submissions", "submission_count", default=10, show_default=True, type=int)
@click.option("--comments", "comment_count", default=1000, show_default=True, type=int)
@click.option("--max-depth", default=20, show_default=True, type=int)
@click.option("--batch-size", default=500, show_default=True, type=int)
@click.option("--prefix", default=DEFAULT_PREFIX, show_default=True)
@click.option("--clean", is_flag=True, default=False)
@click.option("--clean-only", is_flag=True, default=False)
def generate_data(
	seed: int,
	user_count: int,
	submission_count: int,
	comment_count: int,
	max_depth: int,
	batch_size: int,
	prefix: str,
	clean: bool,
	clean_only: bool,
):
	results = generate_data_worker(
		seed=seed,
		users=user_count,
		submissions=submission_count,
		comments=comment_count,
		max_depth=max_depth,
		batch_size=batch_size,
		clean=clean,
		clean_only=clean_only,
		prefix=prefix,
	)

	if clean or clean_only:
		click.echo(
			"Cleaned "
			f"{results['users']} users, "
			f"{results['submissions']} submissions, "
			f"{results['comments']} comments."
		)

	if not clean_only:
		click.echo(
			"Created "
			f"{results['created_users']} users, "
			f"{results['created_submissions']} submissions, "
			f"{results['created_comments']} comments."
		)
