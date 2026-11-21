import os
import json
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "exam_arena.db")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("EXAM_ARENA_SECRET_KEY", secrets.token_hex(32)),
    DATABASE=DATABASE,
)

STUDENTS = [
    ("eugenia.o", "Eugenia O."),
    ("mathew.u", "Mathew U."),
    ("praise.a", "Praise A."),
    ("chika.n", "Chika N."),
    ("daniel.k", "Daniel K."),
    ("amara.i", "Amara I."),
    ("samuel.t", "Samuel T."),
    ("fatima.b", "Fatima B."),
    ("oliver.m", "Oliver M."),
    ("grace.p", "Grace P."),
    ("kofi.d", "Kofi D."),
    ("adaeze.e", "Adaeze E."),
    ("noah.r", "Noah R."),
    ("zainab.s", "Zainab S."),
    ("brian.c", "Brian C."),
]

QUIZZES = [
    {
        "title": "Software Engineering Fundamentals",
        "description": "Test your knowledge of the principles and practices behind reliable software.",
        "time_limit": 120,
        "questions": [
            ("What is the primary purpose of requirements analysis?",
             ["To define what the system should do", "To choose a programming language", "To write the user manual", "To deploy the application"], 0),
            ("Which development model is organized into repeated, incremental cycles?",
             ["Waterfall", "Spiral", "Big-bang", "Code-and-fix"], 1),
            ("In object-oriented design, what does encapsulation do?",
             ["Combines data and methods while controlling access", "Creates copies of every object", "Removes all dependencies", "Converts code into machine language"], 0),
            ("What is the main goal of unit testing?",
             ["Check individual components in isolation", "Measure customer satisfaction", "Verify the production environment", "Document every requirement"], 0),
            ("Which practice helps teams integrate code changes frequently?",
             ["Continuous integration", "Manual deployment", "Big-bang integration", "Pair-free coding"], 0),
            ("What does a software version-control system primarily track?",
             ["Changes to files over time", "Network traffic", "Customer invoices", "Runtime memory usage"], 0),
            ("Which diagram commonly shows interactions between objects over time?",
             ["Sequence diagram", "Pie chart", "Class hierarchy tree", "Deployment checklist"], 0),
            ("What is refactoring?",
             ["Improving internal code structure without changing behavior", "Adding a new product feature", "Deleting the test suite", "Rewriting requirements after release"], 0),
            ("Why are acceptance tests performed?",
             ["To check that the product meets user or business needs", "To benchmark a single function", "To format source files", "To create database indexes"], 0),
            ("Which quality attribute describes how easily software can be modified?",
             ["Maintainability", "Portability", "Usability", "Availability"], 0),
        ],
    },
    {
        "title": "Quick Speed Check",
        "description": "A fast ten-question challenge. Keep an eye on the clock!",
        "time_limit": 15,
        "questions": [
            ("What does CPU stand for?", ["Central Processing Unit", "Computer Personal Utility", "Core Program Upload", "Central Print Unit"], 0),
            ("Which language is primarily used to style web pages?", ["HTML", "CSS", "SQL", "Python"], 1),
            ("How many bits are in a byte?", ["4", "8", "16", "32"], 1),
            ("Which one is a relational database?", ["SQLite", "Redis", "Memcached", "RabbitMQ"], 0),
            ("What does HTTP stand for?", ["Hypertext Transfer Protocol", "High Transfer Text Process", "Host Tracking Transfer Program", "Hyperlink Terminal Text Protocol"], 0),
            ("Which symbol commonly starts a Python comment?", ["//", "#", "<!--", ";;"], 1),
            ("What is the result of 5 × 3?", ["8", "12", "15", "20"], 2),
            ("Which data structure follows FIFO order?", ["Stack", "Queue", "Tree", "Graph"], 1),
            ("Which HTML element creates a hyperlink?", ["<a>", "<p>", "<img>", "<h1>"], 0),
            ("What does RAM provide to a running computer?", ["Temporary working memory", "Permanent file storage", "Internet access", "Power regulation"], 0),
        ],
    },
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def utc_now():
    return datetime.now(timezone.utc)


def as_utc_iso(value):
    return value.isoformat(timespec="microseconds")


def init_db():
    db = sqlite3.connect(app.config["DATABASE"])
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS quizzes (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL,
            time_limit INTEGER NOT NULL CHECK(time_limit > 0),
            question_count INTEGER NOT NULL CHECK(question_count = 10)
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY,
            quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
            question_text TEXT NOT NULL,
            options_json TEXT NOT NULL,
            correct_option INTEGER NOT NULL CHECK(correct_option BETWEEN 0 AND 3),
            position INTEGER NOT NULL,
            UNIQUE(quiz_id, position)
        );
        CREATE TABLE IF NOT EXISTS attempts (
            id INTEGER PRIMARY KEY,
            student_id INTEGER NOT NULL REFERENCES students(id),
            quiz_id INTEGER NOT NULL REFERENCES quizzes(id),
            started_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('started', 'completed', 'expired')),
            score INTEGER,
            share_token TEXT UNIQUE,
            submitted_at TEXT,
            UNIQUE(student_id, quiz_id)
        );
        CREATE TABLE IF NOT EXISTS answers (
            attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id),
            selected_option INTEGER NOT NULL CHECK(selected_option BETWEEN 0 AND 3),
            PRIMARY KEY(attempt_id, question_id)
        );
        """
    )
    for username, name in STUDENTS:
        db.execute(
            "INSERT OR IGNORE INTO students (username, name) VALUES (?, ?)",
            (username, name),
        )
    for quiz in QUIZZES:
        db.execute(
            "INSERT OR IGNORE INTO quizzes (title, description, time_limit, question_count) "
            "VALUES (?, ?, ?, 10)",
            (quiz["title"], quiz["description"], quiz["time_limit"]),
        )
        quiz_id = db.execute(
            "SELECT id FROM quizzes WHERE title = ?", (quiz["title"],)
        ).fetchone()[0]
        for position, (text, options, correct) in enumerate(quiz["questions"], start=1):
            db.execute(
                "INSERT OR IGNORE INTO questions "
                "(quiz_id, question_text, options_json, correct_option, position) "
                "VALUES (?, ?, ?, ?, ?)",
                (quiz_id, text, __import__("json").dumps(options), correct, position),
            )
    db.commit()
    db.close()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "student_id" not in session:
            return redirect(url_for("home"))
        return view(*args, **kwargs)

    return wrapped


def current_student():
    return get_db().execute(
        "SELECT id, username, name FROM students WHERE id = ?",
        (session.get("student_id"),),
    ).fetchone()


@app.context_processor
def inject_nav_student():
    return {
        "nav_student": current_student() if session.get("student_id") else None
    }


def quiz_or_404(quiz_id):
    quiz = get_db().execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if quiz is None:
        abort(404)
    return quiz


@app.route("/", methods=["GET", "POST"])
def home():
    db = get_db()
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        student = db.execute(
            "SELECT id FROM students WHERE username = ?", (username,)
        ).fetchone()
        if student is None:
            flash("That username was not found. Choose a seeded student or try again.", "error")
        else:
            session.clear()
            session["student_id"] = student["id"]
            return redirect(url_for("home"))
    student = current_student() if session.get("student_id") else None
    quizzes = []
    if student:
        quizzes = db.execute(
            """
            SELECT q.*,
                   a.status AS attempt_status,
                   a.score AS attempt_score
            FROM quizzes q
            LEFT JOIN attempts a ON a.quiz_id = q.id AND a.student_id = ?
            ORDER BY q.id
            """,
            (student["id"],),
        ).fetchall()
    students = db.execute("SELECT username, name FROM students ORDER BY name").fetchall()
    return render_template("home.html", student=student, quizzes=quizzes, students=students)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.get("/quiz/<int:quiz_id>")
@login_required
def quiz_rules(quiz_id):
    quiz = quiz_or_404(quiz_id)
    attempt = get_db().execute(
        "SELECT status FROM attempts WHERE student_id = ? AND quiz_id = ?",
        (session["student_id"], quiz_id),
    ).fetchone()
    return render_template("rules.html", quiz=quiz, attempted=attempt is not None)


@app.post("/quiz/<int:quiz_id>/start")
@login_required
def start_quiz(quiz_id):
    quiz = quiz_or_404(quiz_id)
    db = get_db()
    question_count = db.execute(
        "SELECT COUNT(*) FROM questions WHERE quiz_id = ?", (quiz_id,)
    ).fetchone()[0]
    if quiz["question_count"] != 10 or question_count != 10:
        abort(500, "Quiz configuration must contain exactly 10 questions.")
    try:
        db.execute(
            "INSERT INTO attempts (student_id, quiz_id, started_at, status) "
            "VALUES (?, ?, ?, 'started')",
            (session["student_id"], quiz_id, as_utc_iso(utc_now())),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        flash(
            "Refused: You have already attempted this quiz. Only one attempt per person is allowed.",
            "error",
        )
        return redirect(url_for("quiz_rules", quiz_id=quiz_id))
    return redirect(url_for("take_quiz", quiz_id=quiz_id))


@app.get("/quiz/<int:quiz_id>/take")
@login_required
def take_quiz(quiz_id):
    quiz = quiz_or_404(quiz_id)
    db = get_db()
    attempt = db.execute(
        "SELECT * FROM attempts WHERE student_id = ? AND quiz_id = ?",
        (session["student_id"], quiz_id),
    ).fetchone()
    if attempt is None:
        return redirect(url_for("quiz_rules", quiz_id=quiz_id))
    if attempt["status"] != "started":
        flash("This attempt is already closed.", "error")
        return redirect(url_for("quiz_rules", quiz_id=quiz_id))
    questions = db.execute(
        "SELECT id, question_text, options_json, position FROM questions "
        "WHERE quiz_id = ? ORDER BY position",
        (quiz_id,),
    ).fetchall()
    public_questions = [
        {
            "id": question["id"],
            "question_text": question["question_text"],
            "options": json.loads(question["options_json"]),
            "position": question["position"],
        }
        for question in questions
    ]
    deadline = datetime.fromisoformat(attempt["started_at"])
    remaining = max(
        0,
        quiz["time_limit"] - int((utc_now() - deadline).total_seconds()),
    )
    return render_template(
        "take.html", quiz=quiz, questions=public_questions, remaining=remaining
    )


@app.post("/quiz/<int:quiz_id>/submit")
@login_required
def submit_quiz(quiz_id):
    quiz = quiz_or_404(quiz_id)
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    attempt = db.execute(
        "SELECT * FROM attempts WHERE student_id = ? AND quiz_id = ?",
        (session["student_id"], quiz_id),
    ).fetchone()
    if attempt is None:
        return redirect(url_for("quiz_rules", quiz_id=quiz_id))
    if attempt["status"] != "started":
        flash(
            "Refused: You have already attempted this quiz. Only one attempt per person is allowed.",
            "error",
        )
        return redirect(url_for("quiz_rules", quiz_id=quiz_id))
    deadline = datetime.fromisoformat(attempt["started_at"]) + timedelta(
        seconds=quiz["time_limit"]
    )
    if utc_now() > deadline:
        db.execute(
            "UPDATE attempts SET status = 'expired', submitted_at = ? WHERE id = ?",
            (as_utc_iso(utc_now()), attempt["id"]),
        )
        db.commit()
        return render_template(
            "error.html",
            message="Refused: Time limit exceeded. Late submissions are not accepted.",
            back_url=url_for("home"),
        ), 403

    questions = db.execute(
        "SELECT id, correct_option FROM questions WHERE quiz_id = ?", (quiz_id,)
    ).fetchall()
    if len(questions) != 10:
        abort(500, "Quiz configuration must contain exactly 10 questions.")
    submitted = {}
    for question in questions:
        raw = request.form.get("answer_" + str(question["id"]))
        if raw is not None:
            try:
                choice = int(raw)
            except ValueError:
                abort(400, "Invalid answer option.")
            if choice < 0 or choice > 3:
                abort(400, "Invalid answer option.")
            submitted[question["id"]] = choice
    score = sum(
        1 for question in questions
        if submitted.get(question["id"]) == question["correct_option"]
    )
    token = secrets.token_urlsafe(24)
    now = as_utc_iso(utc_now())
    db.execute(
        "UPDATE attempts SET status = 'completed', score = ?, share_token = ?, submitted_at = ? "
        "WHERE id = ? AND status = 'started'",
        (score, token, now, attempt["id"]),
    )
    for question_id, selected_option in submitted.items():
        db.execute(
            "INSERT INTO answers (attempt_id, question_id, selected_option) VALUES (?, ?, ?)",
            (attempt["id"], question_id, selected_option),
        )
    db.commit()
    return redirect(url_for("result", share_token=token))


@app.get("/result/<share_token>")
@login_required
def result(share_token):
    record = get_db().execute(
        """
        SELECT a.*, s.name AS student_name, q.title AS quiz_title
        FROM attempts a
        JOIN students s ON s.id = a.student_id
        JOIN quizzes q ON q.id = a.quiz_id
        WHERE a.share_token = ? AND a.student_id = ? AND a.status = 'completed'
        """,
        (share_token, session["student_id"]),
    ).fetchone()
    if record is None:
        abort(404)
    db = get_db()
    questions = db.execute(
        """
        SELECT qu.id, qu.question_text, qu.options_json, qu.correct_option, qu.position,
               an.selected_option
        FROM questions qu
        JOIN quizzes q ON q.id = qu.quiz_id
        JOIN attempts a ON a.quiz_id = q.id
        LEFT JOIN answers an ON an.attempt_id = a.id AND an.question_id = qu.id
        WHERE a.share_token = ?
        ORDER BY qu.position
        """,
        (share_token,),
    ).fetchall()
    review = [
        {
            "question_text": question["question_text"],
            "options": json.loads(question["options_json"]),
            "correct_option": question["correct_option"],
            "selected_option": question["selected_option"],
        }
        for question in questions
    ]
    return render_template(
        "result.html",
        record=record,
        review=review,
        share_url=url_for("share", share_token=share_token, _external=True),
    )


@app.get("/share/<share_token>")
def share(share_token):
    record = get_db().execute(
        """
        SELECT a.score, a.submitted_at, s.name AS student_name, q.title AS quiz_title
        FROM attempts a
        JOIN students s ON s.id = a.student_id
        JOIN quizzes q ON q.id = a.quiz_id
        WHERE a.share_token = ? AND a.status = 'completed'
        """,
        (share_token,),
    ).fetchone()
    if record is None:
        abort(404)
    return render_template("share.html", record=record)


@app.errorhandler(404)
def not_found(_error):
    return render_template("error.html", message="This page could not be found.", back_url=url_for("home")), 404


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
