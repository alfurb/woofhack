from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from mako.template import Template
import os
import sqlite3
import subprocess
from datetime import datetime
from enum import Enum
from collections import namedtuple
from difflib import ndiff


# create our little application :)
app = Flask(__name__)
app.config.from_object(__name__)

# Load default config and override config from an environment variable
app.config.update(dict(
    DATABASE=os.path.join(app.root_path, 'woofhack.db'),
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

Problem = namedtuple("Problem", ["name", "description", "tests"])

Test = namedtuple("Test", ["name", "inp", "out"])

Result = namedtuple("Result", ["name", "classification", "input", "message", "accepted"])

# Load the problems
problems = {}
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
print (problems)


@app.route("/")
@app.route("/index")
def index():
    db = get_db()
    db.row_factory = sqlite3.Row
    p = db.execute("SELECT id, title, description, created FROM problems")
    return Template(filename="templates/index.html").render(problems=p)

@app.route("/submit/<problem>", methods=['GET', 'POST'])
def submit(problem):
    if problem not in problems:
        abort(404)
    if request.method == 'GET':
        return Template(filename="templates/submit.html").render(name=problem)

    f = request.files['file']

    date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
    path = os.path.join('submissions', problem, date_str)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, 'submitted.cpp')
    f.save(file_path)

    res = run(problem, path, file_path, "c++")
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
        descr = request.form["description"]
        prob_input = request.form["input"]
        prob_output = request.form["output"]
        date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
        db = get_db()
        db.execute('INSERT INTO problems (title, description, created, no_tests) VALUES(?, ?, ?, ?)', (title, descr, date_str, 0))
        db.commit()
    except Exception as e:
        print(e)
        abort(500)

    print(tuple(request.form))
    return Template(filename="templates/new_problem.html").render()

    date_str = datetime.now().strftime("%H:%M:%S-%d-%m-%Y")
    path = os.path.join('submissions', problem, date_str)
    os.makedirs(path, exist_ok=True)
    file_path = os.path.join(path, 'submitted.cpp')
    f.save(file_path)

    res = run(problem, path, file_path, "c++")
    return Template(filename="templates/results.html").render(results=res)

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
