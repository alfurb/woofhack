import os
import sqlite3
import subprocess
import json
import codecs
import functools
import base64
from enum import Enum
from collections import namedtuple
from datetime import datetime
from difflib import ndiff

import markdown2
from passlib.hash import bcrypt_sha256
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash, make_response
from werkzeug.utils import secure_filename
from mako.template import Template
from mako.lookup import TemplateLookup
from flask_httpauth import HTTPTokenAuth
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import (URLSafeTimedSerializer as Serializer, BadSignature, SignatureExpired)


app = Flask(__name__, static_url_path='/static')
app.config.from_object(__name__)
auth = HTTPTokenAuth(scheme='Token')

# Load default config and override config from an environment variable
app.config.update(dict(
    #DATABASE=os.path.join(app.root_path, 'woofhack.db'),
    SECRET_KEY=b'\x12\xa7\xfc\x0b\xcdm\xdb\xde\x7f\xa76a\x0b\x1e\xbc\x15\xa4\xbc\xec\x01\xd4i\x8c\x90',
))

app.config.from_envvar('FLASKR_SETTINGS', silent=True)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///woofhack.db'

db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    pw_hash = db.Column(db.String(64))
    admin = db.Column(db.Boolean())

    def __init__(self, username, pw_hash, admin=False):
        self.username = username
        self.pw_hash = pw_hash
        self.admin = admin

    def __repr__(self):
        return '<User %r>' % self.username

    def generate_auth_token(self):
        s = Serializer(app.config['SECRET_KEY'])
        t = s.dumps({'username': self.username})
        return t


class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), unique=True)
    summary = db.Column(db.String(80), unique=True)
    description = db.Column(db.Text())
    created = db.Column(db.Date())

    def __init__(self, title, description, summary, created):
        self.title = title
        self.summary = summary
        self.description = description
        self.created = created

    def __repr__(self):
        return '<Problem %r>' % self.title

class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    inp = db.Column(db.Text())
    out = db.Column(db.Text())
    test_type = db.Column(db.Text())

    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'))
    problem = db.relationship('Problem', backref=db.backref('tests', lazy='dynamic'))

    def __init__(self, name, inp, out, test_type, problem):
        self.name = name
        self.inp = inp
        self.out = out
        self.test_type = test_type
        self.problem = problem

    def __repr__(self):
        return '<TestCase %r>' % self.name

class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    classification = db.Column(db.String(100))
    submission_folder_path = db.Column(db.Text())

    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'))
    problem = db.relationship('Problem',
        backref=db.backref('submissions', lazy='dynamic'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User',
        backref=db.backref('submissions', lazy='dynamic'))

    def __init__(self, classification, submission_folder_path, user, problem):
        self.classification = classification
        self.submission_folder_path = submission_folder_path
        self.user = user
        self.problem = problem

    def __repr__(self):
        return '<Submission %r>' % self.name

class AdminCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code_hash = db.Column(db.String(64))

    def __init__(self, code_hash):
        self.code_hash = code_hash

    def __repr__(self):
        return '<AdminCode %r>' % self.code_hash

class Alert:
    def __init__(self, alert_header, alert_type, alert_message):
        self.alert_header = alert_header
        self.alert_type = alert_type
        self.alert_message = alert_message


# Specify classes
class Classification():
    Accepted = "Accepted"
    Denied = "Denied"
    Error = "Error"


Test = namedtuple("Test", ["name", "inp", "out"])

Result = namedtuple("Result", ["name", "classification", "input", "message", "accepted"])


# Wrapper to add a header to all Templates
lookup = TemplateLookup(directories=['./templates'])

# Alerts to display next time a page is served
alerts = []
def add_alert(alert):
    alerts.append(alert)

def serve_template(templatename, **kwargs):
    template = lookup.get_template(templatename)
    user = None
    if "session_token" in session:
        user = verify_token(session.get("session_token"))

    send_alerts = list(alerts)
    global alerts
    alerts = list([])
    return template.render(url_for=url_for,
                           templatename=templatename,
                           user=user,
                           alerts=send_alerts,
                           **kwargs)

def login_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not "session_token" in session:
            abort(401)
        g.user = verify_token(session["session_token"])
        if g.user != None:
            return f(*args, **kwargs)
        else:
            abort(401)

    return wrapped

# A decorator for requiring admin privileges on routes
def admin_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not g.user.admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapped

# Used to verify passwords submitted with those stored in our database
def verify_password(username, password):
    user = User.query.filter_by(username = username).first()
    try:
        if not user or not bcrypt_sha256.verify(password, user.pw_hash):
            return False
    except ValueError:
        return False
    g.user = user
    return True


def verify_token(token):
    s = Serializer(app.config['SECRET_KEY'])
    try:
        data = s.loads(token)
    except SignatureExpired:
        return None  # valid token, but expired
    except BadSignature:
        return None  # invalid token
    user = User.query.filter_by(username=data['username']).first()
    return user


@app.route("/")
@app.route("/index")
def index():
    p = Problem.query.all()
    return serve_template("index.html", problems=p)


@app.errorhandler(404)
def lost(e=None):
    return serve_template("lost.html")

@app.errorhandler(401)
@app.route("/login", methods=["GET", "POST"])
def login(e=None):
    if e:
        add_alert(Alert("Warning", "warning", "Tried to access unauthorized resource, log in first."))
    if request.method == "GET":
        return serve_template("login.html")

    username = request.form.get("username")
    password = request.form.get("password")
    if verify_password(username, password):
        session["session_token"] = g.user.generate_auth_token()
        add_alert(Alert("Success", "success", "User logged in"))
        return redirect("index")
    else:
        add_alert(Alert('Error', 'danger', 'Wrong password for user ' + str(username)))
        return serve_template('login.html')

@app.route("/logout", methods=["GET", "POST"])
def logout():
    if not "session_token" in session or session["session_token"] is None:
        add_alert(Alert("Warning", "warning", "No user was logged in"))
        return redirect('login')
    else:
        user = verify_token(session["session_token"])
        del session["session_token"]
        add_alert(Alert("Success", "success", "User logged out"))
        return redirect('login')

@app.route("/static/<item>")
def statix_file(item):
    return app.send_static_file(item)


@app.route('/register', methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return serve_template("register.html")

    username = request.form.get("username")
    password = request.form.get("password")
    password_repeated = request.form.get("password_repeated")
    admin_code = request.form.get("code")
    admin_value = False

    if not username or not password or not password_repeated:
        add_alert(Alert("Error", "danger", "All fields must be filled out."))
        return serve_template("register.html")

    if password != password_repeated:
        add_alert(Alert("Error", "danger", "Passwords must match."))
        return serve_template("register.html")

    # User already exists
    if User.query.filter_by(username = username).first():
        add_alert(Alert("Error", "danger", "User already exists."))
        return serve_template("register.html")

    if request.form.get("admin"):
        if check_admin_code(admin_code):
            admin_value = True
        else:
            add_alert(Alert("Error", "danger", "Wrong or no Admin Code."))
            return serve_template("register.html")

    try:
        password = bcrypt_sha256.hash(password)
        user = User(username, password, admin=admin_value)
        db.session.add(user)
        db.session.commit()
        if admin_value:
            add_alert(Alert("Success", "success", "New Admin registered"))
            return redirect("index")
        else:
            add_alert(Alert("Success", "success", "New User registered"))
            return redirect("index")
    except Exception as e:
        db.session.rollback()
        abort(500)

def check_admin_code(admin_code):
    code_hashes = AdminCode.query.all()
    for c in code_hashes:
        if bcrypt_sha256.verify(admin_code, c.code_hash):
            return True
    return False

@app.route('/scoreboard', methods=["GET"])
def scoreboard():
    # Create mapping from each user to the list of problems and the classification they have
    problems = Problem.query.all()
    users = User.query.all()
    # [("sigurjon", [("sum", "Denied"), ("minus", "Accepted")])]
    user_mappings = []
    for user in users:
        probs = []
        solved = 0
        for problem in problems:
            if any(x.user == user and x.classification == Classification.Accepted for x in problem.submissions):
                probs.append(("green", Classification.Accepted))
                solved += 1
            elif any(x.user == user and x.classification == Classification.Denied for x in problem.submissions):
                probs.append(("goldenrod", Classification.Denied))
            elif any(x.user == user and x.classification == Classification.Error for x in problem.submissions):
                probs.append(("red", Classification.Error))
            else:
                probs.append(("grey", "Not tried"))
        # Only add people to the scoreboard that have tried a problem
        if not all([text == "Not tried" for color, text in probs]):
            user_mappings.append((user.username, probs, solved))
    # Sort by number of solved problems, bigger first
    user_mappings.sort(key=lambda x: -x[2])
    user_mappings = [(color, text) for color, text, solved in user_mappings]
    return serve_template("scoreboard.html", problems=problems, user_mappings=user_mappings)

@app.route("/submit/<title>", methods=['GET', 'POST'])
@login_required
def submit(title):
    prob = Problem.query.filter_by(title = title).first()
    if not prob:
        abort(404)
    if request.method == 'GET':
        tests = TestCase.query.filter_by(problem_id=prob.id, test_type="example")
        return serve_template("submit.html", prob=prob, tests=tests)

    language = request.form.get("language")

    f = request.files.get('file')
    filename = secure_filename(f.filename)
    if not filename:
        abort(400)

    date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
    path = os.path.join('submissions', title, date_str)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, filename)
    f.save(file_path)

    classified, res = run(prob, path, file_path, language)
    # Get the current user from the global namespace, it is set in verify_password
    user = g.user

    # Add the submission to database
    submission = Submission(classified, path, user, prob)
    db.session.add(submission)
    db.session.commit()
    return serve_template("results.html", results=res)

def run(problem, submission_folder_path, file_path, language):
    """returns a tuple of classification and a list of tuples (test, classification, message, accepted)"""
    # Compile and set the commands to run a file
    if language == "c++":
        output_path = os.path.join(submission_folder_path, 'compiled')
        p = subprocess.Popen(["g++", "-o", output_path, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        output = p.communicate()
        if output[1]:
            error = output[1].decode()
            # If we unsuccessfully compile we send back a list with one element
            return (Classification.Error, [Result("Compilation", Classification.Error, "", error, False)])
        run_commands = ["./" + output_path]
    elif language == "python3":
        run_commands = ["python3", file_path]
    elif language == "python2":
        run_commands = ["python", file_path]

    # Run tests
    results = []
    for test in problem.tests.filter_by(test_type="test"):
        p = subprocess.Popen(run_commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        output = p.communicate(input=test.inp.encode())
        # Convert byte string to utf8 string
        stdout = output[0].decode().strip()
        if p.returncode != 0:
            error = output[1].decode()
            res = Result(test.name, Classification.Error, "", error, False)
        elif stdout == test.out:
            res = Result(test.name, Classification.Accepted, "", "", True)
        else:
            feedback = ndiff(stdout.splitlines(), test.out.splitlines())
            feedback = map(lambda x: (x, "red" if x.startswith("- ") else "green" if x.startswith("+ ") else "grey"), feedback)
            feedback = ["<span style='color:" + color + "'>" + text + "</span>" for text, color in feedback]
            feedback = "\n".join(feedback)
            res = Result(test.name, Classification.Denied, test.inp, feedback, False)
        results.append(res)
    classified = Classification.Accepted if all(test[1] == Classification.Accepted for test in results) else ""
    classified = Classification.Denied if any(test[1] == Classification.Denied for test in results) else classified
    classified = Classification.Error if any(test[1] == Classification.Error for test in results) else classified
    return (classified, results)


@app.route("/new_problem", methods=['GET', 'POST'])
@login_required
@admin_required
def new_problem():
    if request.method == 'GET':
        return serve_template("new_problem.html")

    title = request.form.get("title")
    summary = request.form.get("summary")
    descr = request.files.get("description")
    examples = request.files.get("testcases")

    if not all([title, summary, descr, examples]):
        add_alert(Alert("Error", "danger", "All fields must be included."))
        return serve_template("new_problem.html")

    if Problem.query.filter_by(title=title).first() != None:
        add_alert(Alert("Error", "danger", "A problem with that name already exists."))
        return serve_template("new_problem.html")

    descr = description_to_html(descr)

    prob = Problem(title, descr, summary, datetime.now())
    db.session.add(prob)

    insert_tests_from_json(examples, db, prob)
    db.session.commit()
    add_alert(Alert('Success', 'success', 'New problem saved'))
    return serve_template("new_problem.html")

def description_to_html(descr):
    return markdown2.markdown(descr.read().decode('utf-8'))


def insert_tests_from_json(file, db, prob):
    f = json.loads(file.read().decode('utf-8'))
    for x in f:
        db.session.add(TestCase(x['name'], x['input'], x['output'], x['type'], prob))

if __name__ == "__main__":
    context = ('server.key.crt', 'server.key.key')
    app.run(debug=False, ssl_context=context)
