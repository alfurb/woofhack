from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from mako.template import Template
import os
import sqlite3
import subprocess
from enum import Enum


# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'flaskr.db'),
    SECRET_KEY='development key',
    USERNAME='admin',
    PASSWORD='default'
))
app.config.from_envvar('FLASKR_SETTINGS', silent=True)

# Specify classes
class Classification():
    Accepted = "Accepted"
    Denied = "Denied"
    Error = "Error"

class Problem():
    name = ""
    description = ""
    tests = []
    def __init__(self):
        self.tests = list([])
    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)
    def __repr__(self):
        return str(self)

class Test():
    name = ""
    inp = ""
    out = ""
    def __str__(self):
        return str(self.__class__) + ": " + str(self.__dict__)
    def __repr__(self):
        return str(self)

# Load the problems
problems = {}
for name in os.listdir('problems'):
    base_path = os.path.join('problems', name)
    problem = Problem()
    problem.name = name
    with open(os.path.join(base_path, 'description.html')) as f:
        problem.description = f.read()
    has_solution = os.path.exists(os.path.join(base_path, 'solution.py'))
    test_base_dir = os.path.join(base_path, 'tests')
    assert os.path.exists(test_base_dir)
    for tname in os.listdir(test_base_dir):
        test_dir = os.path.join(test_base_dir, tname)
        test = Test()
        test.name = tname
        # Read input
        test.inp = os.path.join(test_dir, 'in')
        with open(test.inp) as f:
            # Strip trailing newline
            test.inp = f.read().strip()
        # Read in expected output
        test.out = os.path.join(test_dir, 'out')
        with open(test.out) as f:
            # Strip trailing newline
            test.out = f.read().strip()
        problem.tests.append(test)
    problems[name] = problem
print (problems)


@app.route("/")
@app.route("/index")
def index():
    return Template(filename="templates/index.html").render(problems=problems)

@app.route("/submit/<problem>", methods=['GET', 'POST'])
def submit(problem):
    if problem not in problems:
        abort(404)
    if request.method == 'GET':
        return Template(filename="templates/submit.html").render(name=problem)
    f = request.files['file']

    path = os.path.join('submissions', problem)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, 'submitted_solution.cpp')
    f.save(file_path)

    res = run(problem, path, file_path, "c++")
    return Template(filename="templates/result.html").render(
        classification=res[0],
        message=str(res[1], encoding="utf8").replace("\n", "<br>"),
        accepted=res[0] == Classification.Accepted)

def run(problem, submission_folder_path, file_path, language):
    """returns a tuple (classification, message)"""
    if language == "c++":
        output_path = os.path.join(submission_folder_path, 'compiled')
        p = subprocess.Popen(["g++", "-o", output_path, file_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
        output = p.communicate()
        print("compile", output)
        if output[1]:
            return (Classification.Error, output[1])
        accepted = True
        print(problems[problem])
        for i in problems[problem].tests:
            print (i)
        for test in problems[problem].tests:
            p = subprocess.Popen(["./" + output_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
            output = p.communicate(input=test.inp.encode())
            print ("run", output)
            print("res", output[0].decode(), "expected", test.out, "input", test.inp)
            accepted = accepted and output[0].decode() == test.out
        return (Classification.Accepted if accepted else Classification.Denied, output[0])

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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
