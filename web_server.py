from flask import Flask, request, session, g, redirect, url_for, abort, render_template, flash
from mako.template import Template
import os
import sqlite3


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

# Load the problems
problems = {}
for name in os.listdir('problems'):
    base_path = os.path.join('problems', name)
    problem = {}
    problem["name"] = name
    problem["description"] = ""
    with open(os.path.join(base_path, 'description.html')) as f:
        problem["description"] = f.read()
    problem["tests"] = []
    has_solution = os.path.exists(os.path.join(base_path, 'solution.py'))
    test_base_dir = os.path.join(base_path, 'tests')
    assert os.path.exists(test_base_dir)
    for tname in os.listdir(test_base_dir):
        test_dir = os.path.join(test_base_dir, tname)
        test = {}
        test["name"] = tname
        test["input"] = os.path.join(test_dir, 'in')
        test["output"] = os.path.join(test_dir, 'out')
        assert os.path.exists(test["input"])
        assert has_solution or os.path.exists(test["output"])
        problem["tests"].append(test)
    problems[name] = problem
print (problems)

@app.route("/")
@app.route("/index")
def index():
    return Template(filename="templates/index.html").render(problems=problems)

@app.route("/submit/<problem>", methods=['GET', 'POST'])
def submit(problem):
    if request.method == 'GET':
        return Template(filename="templates/submit.html").render(name=problem)
    f = request.files['file']
    print(f)
    path = os.path.join('submissions', problem)
    os.makedirs(path, exist_ok=True)
    f.save('submissions/{0}/submitted_solution.cpp'.format(problem))
    return redirect("/")

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
