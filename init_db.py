from web_server import *
db.drop_all()
db.create_all()
d = Problem("minus", "print the difference of two numbers", datetime.now())
s = Problem("sum", "print the sum of two numbers", datetime.now())
db.session.add(d)
db.session.add(s)
db.session.commit()
d_tests = [("test 1", "5\n5", "0", "example", d), ("test 2", "15\n5", "10", "test", d), ("test 3", "2\n3", "-1", "test", d)]
for i in d_tests:
    test = TestCase(*i)
    db.session.add(test)
db.session.commit()

d_tests = [("test 1", "5\n5", "10", "example", s), ("test 2", "15\n5", "20", "test", s), ("test 3", "2\n3", "5", "test", s)]
for i in d_tests:
    test = TestCase(*i)
    db.session.add(test)
db.session.commit()

admin = User("admin", "admin", True)
siggi = User("siggi", "siggi", False)
alfur = User("alfur", "alfur", False)
db.session.add(admin)
db.session.add(siggi)
db.session.add(alfur)
db.session.commit()
