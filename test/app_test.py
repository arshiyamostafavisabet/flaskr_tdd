import os
import pytest
from pathlib import Path
import json

from project.app import app, db
from project.models import Post

TEST_DB = "test.db"


@pytest.fixture
def client():
    BASE_DIR = Path(__file__).resolve().parent.parent
    app.config["TESTING"] = True
    app.config["DATABASE"] = BASE_DIR.joinpath(TEST_DB)
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR.joinpath(TEST_DB)}"

    with app.app_context():
        db.create_all()  # setup
        yield app.test_client()  # tests run here
        db.drop_all()  # teardown


def login(client, username, password):
    """Login helper function"""
    return client.post(
        "/login",
        data=dict(username=username, password=password),
        follow_redirects=True,
    )


def logout(client):
    """Logout helper function"""
    return client.get("/logout", follow_redirects=True)


def test_index(client):
    response = client.get("/", content_type="html/text")
    assert response.status_code == 200


def test_database(client):
    """initial test. ensure that the database exists"""
    tester = Path("test.db").is_file()
    assert tester


def test_empty_db(client):
    """Ensure database is blank"""
    rv = client.get("/")
    assert b"No entries yet. Add some!" in rv.data


def test_login_logout(client):
    """Test login and logout using helper functions"""
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"])
    assert b"You were logged in" in rv.data
    rv = logout(client)
    assert b"You were logged out" in rv.data
    rv = login(client, app.config["USERNAME"] + "x", app.config["PASSWORD"])
    assert b"Invalid username" in rv.data
    rv = login(client, app.config["USERNAME"], app.config["PASSWORD"] + "x")
    assert b"Invalid password" in rv.data


def test_messages(client):
    """Ensure that user can post messages"""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.post(
        "/add",
        data=dict(title="<Hello>", text="<strong>HTML</strong> allowed here"),
        follow_redirects=True,
    )
    assert b"No entries here so far" not in rv.data
    assert b"&lt;Hello&gt;" in rv.data
    assert b"<strong>HTML</strong> allowed here" in rv.data


def test_login_delete(client):
    """Ensure deleting a post requires authentication."""
    db.session.query(Post).delete()
    post = Post("Post to delete", "This post should be deleted after login.")
    db.session.add(post)
    db.session.commit()
    assert post.id == 1

    rv = client.get("/delete/1")
    assert rv.status_code == 401
    assert json.loads(rv.data)["status"] == 0
    assert db.session.get(Post, 1) is not None

    login(client, app.config["USERNAME"], app.config["PASSWORD"])
    rv = client.get("/delete/1")
    assert rv.status_code == 200
    assert json.loads(rv.data)["status"] == 1
    assert db.session.get(Post, 1) is None


def test_search(client):
    """Ensure each search keyword only returns matching posts."""
    login(client, app.config["USERNAME"], app.config["PASSWORD"])

    titles_by_keyword = {
        "app": ["apple 1", "apple 2"],
        "oran": ["orange 1", "orange 2"],
        "ban": ["banan 1", "banan 2"],
    }
    all_titles = [title for titles in titles_by_keyword.values() for title in titles]

    for title in all_titles:
        rv = client.post(
            "/add",
            data={"title": title, "text": f"Text for {title}"},
            follow_redirects=True,
        )
        assert rv.status_code == 200

    for keyword, matching_titles in titles_by_keyword.items():
        rv = client.get("/search/", query_string={"query": keyword})
        assert rv.status_code == 200

        correct_count = sum(title.encode() in rv.data for title in matching_titles)
        wrong_count = sum(
            title.encode() in rv.data
            for title in all_titles
            if title not in matching_titles
        )
        assert correct_count == 2
        assert rv.data.count(b'<li class="entry">') == 2
        assert wrong_count == 0
