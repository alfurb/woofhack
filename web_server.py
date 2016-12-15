import os
import sqlite3
import subprocess
import json
import codecs
import functools
import base64
from datetime import datetime
from enum import Enum
from collections import namedtuple
from difflib import ndiff

from passlib.hash import bcrypt_sha256
from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from mako.template import Template
from mako.lookup import TemplateLookup
from flask_httpauth import HTTPBasicAuth
from flask_sqlalchemy import SQLAlchemy

# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
auth = HTTPBasicAuth()

# Load default config and override config from an environment variable
app.config.update(dict(
    #DATABASE=os.path.join(app.root_path, 'woofhack.db'),
    SECRET_KEY=b'\x12\xa7\xfc\x0b\xcdm\xdb\xde\x7f\xa76a\x0b\x1e\xbc\x15\xa4\xbc\xec\x01\xd4i\x8c\x90',
))
app.config.from_envvar('FLASKR_SETTINGS', silent=True)

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

class Problem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), unique=True)
    description = db.Column(db.String(1024))
    created = db.Column(db.Date())

    def __init__(self, title, description, created):
        self.title = title
        self.description = description
        self.created = created

    def __repr__(self):
        return '<Problem %r>' % self.title

class TestCase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    inp = db.Column(db.Text())
    out = db.Column(db.Text())

    problem_id = db.Column(db.Integer, db.ForeignKey('problem.id'))
    problem = db.relationship('Problem',
        backref=db.backref('tests', lazy='dynamic'))

    def __init__(self, name, inp, out, problem):
        self.name = name
        self.inp = inp
        self.out = out
        self.problem = problem

    def __repr__(self):
        return '<TestCase %r>' % self.name

# Specify classes
class Classification():
    Accepted = "Accepted"
    Denied = "Denied"
    Error = "Error"


Test = namedtuple("Test", ["name", "inp", "out"])

Result = namedtuple("Result", ["name", "classification", "input", "message", "accepted"])


# Wrapper to add a header to all Templates
lookup = TemplateLookup(directories=['./templates'])
def serve_template(templatename, **kwargs):
    template = lookup.get_template(templatename)
    return template.render(**kwargs, auth=auth)

# A decorator for requiring admin privileges on routes
def admin_required(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not auth.username():
            abort(403)
        else:
            user = User.query.filter_by(username=auth.username()).first()
            if not user.admin:
                abort(403)
        return f(*args, **kwargs)
    return wrapped

# Used to verify passwords submitted with those stored in our database
@auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username = username).first()
    try:
        if not user or not bcrypt_sha256.verify(password, user.pw_hash):
            return False
    except ValueError:
        return False
    return True

@app.route("/")
@app.route("/index")
def index():
    p = Problem.query.all()
    return serve_template("index.html", problems=p)

@app.route('/register', methods=["GET", "POST"])
def register():
    print(session)
    if request.method == "GET":
        return serve_template("register.html")

    username = request.form.get("username")
    password = request.form.get("password")
    password_repeated = request.form.get("password_repeated")
    if not username or not password or not password_repeated:
        return serve_template("register.html", error="All fields must be filled out")

    if password != password_repeated:
        return serve_template("register.html", error="Passwords do not match")

    # User already exists
    if User.query.filter_by(username = username).first():
        return serve_template("register.html", error="User is already registered")

    try:
        password = bcrypt_sha256.hash(password)
        user = User(username, password)
        db.session.add(user)
        db.session.commit()
        return redirect("/")
    except Exception as e:
        print(e)
        abort(500)

@app.route("/submit/<title>", methods=['GET', 'POST'])
@auth.login_required
def submit(title):
    prob = Problem.query.filter_by(title = title).first()
    if not prob:
        abort(404)
    if request.method == 'GET':
        return serve_template("submit.html", name=prob.title)

    f = request.files['file']

    date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
    path = os.path.join('submissions', title, date_str)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, 'submitted.cpp')
    f.save(file_path)

    res = run(prob, path, file_path, "c++")
    return serve_template("results.html", results=res)

def run(problem, submission_folder_path, file_path, language):
    """returns a list of tuples (test, classification, message, accepted)"""
    if language == "c++":
        output_path = os.path.join(submission_folder_path, 'compiled')
        p = subprocess.Popen(["g++", "-o", output_path, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        output = p.communicate()
        print("compile", output)
        if output[1]:
            error = output[1].decode()
            return [Result("Compilation", Classification.Error, "", error, False)]
        output_path = "./" + output_path
    results = []
    for test in problem.tests:
        p = subprocess.Popen([output_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        output = p.communicate(input=test.inp.encode())
        print("run", output)
        # Convert byte string to utf8 string
        stdout = output[0].decode()
        if p.returncode != 0:
            error = output[1].decode()
            res = Result(test.name, Classification.Error, "", error, False)
        elif stdout == test.out:
            res = Result(test.name, Classification.Accepted, "", "", True)
        else:
            diff = ndiff(test.out.splitlines(), stdout.splitlines())
            diff = map(lambda x: (x, "red" if x.startswith("- ") else "green" if x.startswith("+ ") else "grey"), diff)
            diff = ["<span style='color:" + x[1] + "'>" + x[0] + "</span>" for x in diff]
            diff = "\n".join(diff)
            res = Result(test.name, Classification.Denied, test.inp, diff, False)
        results.append(res)
    return results


@app.route("/new_problem", methods=['GET', 'POST'])
@auth.login_required
@admin_required
def new_problem():
    if request.method == 'GET':
        return serve_template("new_problem.html")
    try:
        title = request.form["title"]
        descr = request.files["description"]
        examples = request.files["example"]
        tests = request.files["tests"]
        date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")

        descr = description_to_html(descr)

        prob = Problem(title, descr, datetime.now())
        db.session.add(prob)
        db.session.commit()
        problem_id = prob.id

        insert_tests_from_json(examples, c, problem_id, 'example')
        insert_tests_from_json(tests, c, problem_id, 'test')
        db.commit()
    except Exception as e:
        print(e)
        abort(500)
    return serve_template("new_problem.html")

def description_to_html(descr):
    # TODO: check if markdown or plaintext and convert to html
    return descr.read().decode('utf-8')

def insert_tests_from_json(file, cursor, problem_id, test_type):
    f = json.loads(file.read().decode('utf-8'))
    f = [(problem_id, x, f[x], test_type) for x in f]
    cursor.executemany('INSERT INTO tests (problem, input, output, test_type) VALUES (?, ?, ?, ?);', f)

if __name__ == "__main__":
    context = ('server.key.crt', 'server.key.key')
    app.run(debug=True, port=5001, ssl_context=context)
