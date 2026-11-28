import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

import app as exam_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    database = tmp_path / "exam_arena.db"
    monkeypatch.setitem(exam_app.app.config, "DATABASE", str(database))
    monkeypatch.setitem(exam_app.app.config, "TESTING", True)
    exam_app.init_db()
    exam_app.app.config["SECRET_KEY"] = "test-secret"

    with exam_app.app.test_client() as test_client:
        yield test_client


def login(client, username="eugenia.o"):
    return client.post("/", data={"username": username})


def quiz_id(database_name, title):
    with sqlite3.connect(database_name) as db:
        return db.execute(
            "SELECT id FROM quizzes WHERE title = ?", (title,)
        ).fetchone()[0]


def start_attempt(client, quiz_id):
    login(client)
    response = client.post(f"/quiz/{quiz_id}/start")
    assert response.status_code == 302
    assert "/take" in response.headers["Location"]


def test_home_shows_students_and_quizzes_to_anonymous(client):
    response = client.get("/")

    assert response.status_code == 200
    assert b"Eugenia O." in response.data
    assert b"Software Engineering Fundamentals" not in response.data


def test_login_invalid_username_and_logout(client):
    invalid = client.post("/", data={"username": "missing.user"})
    assert invalid.status_code == 200
    assert b"That username was not found" in invalid.data

    login(client)
    logged_out = client.post("/logout")
    assert logged_out.status_code == 302


def test_quiz_rules_and_take_routes(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")

    assert client.get(f"/quiz/{quiz}/").status_code == 404
    assert client.get(f"/quiz/{quiz}").status_code == 302

    login(client)
    rules = client.get(f"/quiz/{quiz}")
    assert rules.status_code == 200

    start_attempt(client, quiz)
    take = client.get(f"/quiz/{quiz}/take")
    assert take.status_code == 200
    assert b"What is the primary purpose of requirements analysis?" in take.data
    assert b"correct_option" not in take.data


def test_submit_scores_all_answers(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")
    start_attempt(client, quiz)

    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        db.row_factory = sqlite3.Row
        questions = db.execute(
            "SELECT id, correct_option FROM questions "
            "WHERE quiz_id = ? ORDER BY position",
            (quiz,),
        ).fetchall()

    answers = {
        f"answer_{question['id']}": str(question["correct_option"])
        for question in questions
    }
    response = client.post(f"/quiz/{quiz}/submit", data=answers)

    assert response.status_code == 302
    share_token = response.headers["Location"].rsplit("/", 1)[-1]
    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        db.row_factory = sqlite3.Row
        attempt = db.execute(
            "SELECT status, score, share_token FROM attempts "
            "WHERE student_id = (SELECT id FROM students WHERE username = 'eugenia.o') "
            "AND quiz_id = ?",
            (quiz,),
        ).fetchone()

    assert attempt["status"] == "completed"
    assert attempt["score"] == 10
    assert attempt["share_token"] == share_token


def test_submit_with_missing_answers_scores_zero(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Quick Speed Check")
    start_attempt(client, quiz)

    response = client.post(f"/quiz/{quiz}/submit", data={})

    assert response.status_code == 302
    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        score = db.execute(
            "SELECT score FROM attempts "
            "WHERE student_id = (SELECT id FROM students WHERE username = 'eugenia.o') "
            "AND quiz_id = ?",
            (quiz,),
        ).fetchone()[0]
    assert score == 0


def test_submit_partial_answers_scores_only_correct_choices(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")
    start_attempt(client, quiz)

    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        db.row_factory = sqlite3.Row
        questions = db.execute(
            "SELECT id, correct_option FROM questions "
            "WHERE quiz_id = ? ORDER BY position",
            (quiz,),
        ).fetchall()

    answers = {
        f"answer_{questions[index]['id']}": str(questions[index]["correct_option"])
        for index in range(3)
    }
    answers[f"answer_{questions[3]['id']}"] = "3"
    response = client.post(f"/quiz/{quiz}/submit", data=answers)

    assert response.status_code == 302
    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        score = db.execute(
            "SELECT score FROM attempts "
            "WHERE student_id = (SELECT id FROM students WHERE username = 'eugenia.o') "
            "AND quiz_id = ?",
            (quiz,),
        ).fetchone()[0]
    assert score == 3


@pytest.mark.parametrize("invalid_choice", ["-1", "4", "not-a-number"])
def test_submit_rejects_invalid_answer_options(client, invalid_choice):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")
    start_attempt(client, quiz)

    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        question_id = db.execute(
            "SELECT id FROM questions WHERE quiz_id = ? ORDER BY position LIMIT 1",
            (quiz,),
        ).fetchone()[0]

    response = client.post(
        f"/quiz/{quiz}/submit",
        data={f"answer_{question_id}": invalid_choice},
    )
    assert response.status_code == 400


def test_submit_after_deadline_is_refused(client, monkeypatch):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Quick Speed Check")
    start_attempt(client, quiz)

    deadline_passed = datetime.now(timezone.utc) + timedelta(minutes=16)
    monkeypatch.setattr(exam_app, "utc_now", lambda: deadline_passed)
    response = client.post(f"/quiz/{quiz}/submit", data={})

    assert response.status_code == 403
    assert b"Time limit exceeded" in response.data
    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        status = db.execute(
            "SELECT status FROM attempts "
            "WHERE student_id = (SELECT id FROM students WHERE username = 'eugenia.o') "
            "AND quiz_id = ?",
            (quiz,),
        ).fetchone()[0]
    assert status == "expired"


def test_duplicate_start_is_refused(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")
    start_attempt(client, quiz)

    response = client.post(f"/quiz/{quiz}/start")
    assert response.status_code == 302
    assert f"/quiz/{quiz}" in response.headers["Location"]

    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        count = db.execute(
            "SELECT COUNT(*) FROM attempts "
            "WHERE student_id = (SELECT id FROM students WHERE username = 'eugenia.o') "
            "AND quiz_id = ?",
            (quiz,),
        ).fetchone()[0]
    assert count == 1


def test_result_and_public_share_routes(client):
    quiz = quiz_id(exam_app.app.config["DATABASE"], "Software Engineering Fundamentals")
    start_attempt(client, quiz)

    with sqlite3.connect(exam_app.app.config["DATABASE"]) as db:
        db.row_factory = sqlite3.Row
        questions = db.execute(
            "SELECT id, correct_option FROM questions "
            "WHERE quiz_id = ? ORDER BY position",
            (quiz,),
        ).fetchall()

    response = client.post(
        f"/quiz/{quiz}/submit",
        data={
            f"answer_{question['id']}": str(question["correct_option"])
            for question in questions
        },
    )
    token = response.headers["Location"].rsplit("/", 1)[-1]

    result = client.get(f"/result/{token}")
    assert result.status_code == 200
    assert b"Eugenia O." in result.data

    client.post("/logout")
    share = client.get(f"/share/{token}")
    assert share.status_code == 200
    assert b"Eugenia O." in share.data
    assert client.get("/share/not-a-valid-token").status_code == 404

