from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from mako.template import Template
import os
import sqlite3
import subprocess
import json
import markdown2
from datetime import datetime
from enum import Enum
from collections import namedtuple
from difflib import ndiff

from flask_httpauth import HTTPBasicAuth
from flask_sqlalchemy import SQLAlchemy

# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)
auth = HTTPBasicAuth()

# Load default config and override config from an environment variable
app.config.update(dict(
    #DATABASE=os.path.join(app.root_path, 'woofhack.db'),
    SECRET_KEY='development key',
    USERNAME='admin',
    PASSWORD='default'
))
app.config.from_envvar('FLASKR_SETTINGS', silent=True)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///woofhack.db'
db = SQLAlchemy(app)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    pw_hash = db.Column(db.String(64))
    admin = db.Column(db.Date())

    def __init__(self, username, pw_hash, admin):
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
        self.inp = name
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

# Load the problems
'''problems = {}
for name in os.listdir('problems'):
    base_path = os.path.join('problems', name)
    with open(os.path.join(base_path, 'description.html')) as f:
        description = f.read()
    has_solution = os.path.exists(os.path.join(base_path, 'solution.py'))
    test_base_dir = os.path.join(base_path, 'tests')
    assert os.path.exists(test_base_dir)

    tests = []
    for tname in os.listdir(test_base_dir):
        test_dir = os.path.join(test_base_dir, tname)
        # Read input
        inp = os.path.join(test_dir, 'in')
        with open(inp) as f:
            # Strip trailing newline
            inp = f.read().strip()
        # Read in expected output
        out = os.path.join(test_dir, 'out')
        with open(out) as f:
            # Strip trailing newline
            out = f.read().strip()
        tests.append(Test(tname, inp, out))

    problems[name] = Problem(name, description, tests)
print (problems)'''

@app.route("/")
@app.route("/index")
def index():
    p = Problem.query.all()
    return Template(filename="templates/index.html").render(problems=p)

@auth.verify_password
def verify_password(username, password):
    user = User.query.filter_by(username = username).first()
    if not user or not user.pw_hash == password:
        return False
    g.user = user
    return True

@app.route('/safe')
@auth.login_required
def safe():
    print(User.query.all())
    return "Hello, %s!" % auth.username()


@app.route("/submit/<title>", methods=['GET', 'POST'])
def submit(title):
    prob = Problem.query.filter_by(title = title).first()
    if not prob:
        abort(404)
    if request.method == 'GET':
        return Template(filename="templates/submit.html").render(name=prob.title)

    f = request.files['file']

    date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
    path = os.path.join('submissions', title, date_str)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, 'submitted.cpp')
    f.save(file_path)

    res = run(prob, path, file_path, "c++")
    return Template(filename="templates/results.html").render(results=res)

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
    for test in problems[problem].tests:
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
def new_problem():
    if request.method == 'GET':
        return Template(filename="templates/new_problem.html").render()
    try:
        title = request.form["title"]
        descr = request.files["description"]
        examples = request.files["example"]
        tests = request.files["tests"]
        date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")

        descr = description_to_html(descr)
        print(descr)

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
    return Template(filename="templates/new_problem.html").render()

def description_to_html(descr):
    # TODO: check if markdown or plaintext and convert to html
    return markdown2.markdown(descr.read().decode('utf-8'))

def insert_tests_from_json(file, cursor, problem_id, test_type):
    f = json.loads(file.read().decode('utf-8'))
    f = [(problem_id, x, f[x], test_type) for x in f]
    cursor.executemany('INSERT INTO tests (problem, input, output, test_type) VALUES (?, ?, ?, ?);', f)

'''
def connect_db():
    """Connects to the specific database."""
    rv = sqlite3.connect(app.config['DATABASE'])
    rv.row_factory = sqlite3.Row
    return rv


def get_db():
    """Opens a new database connection if there is none yet for the
    current application context.
    """
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db


@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()


def init_db():
    db = get_db()
    with app.open_resource('schema.sql', mode='r') as f:
        db.cursor().executescript(f.read())
    db.commit()


@app.cli.command('initdb')
def initdb_command():
    """Initializes the database."""
    init_db()
    print('Initialized the database.')
'''

if __name__ == "__main__":
    app.run(debug=True, port=5001)
