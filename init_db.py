from web_server import *
db.drop_all()
db.create_all()
d = Problem("minus", "print the difference of two numbers", "Find the difference of two numbers", datetime.now())
s = Problem("sum", "print the sum of two numbers", "Find the sum of two numbers", datetime.now())
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

admin = User("admin", bcrypt_sha256.hash("admin"), True)
siggi = User("siggi", bcrypt_sha256.hash("siggi"), False)
alfur = User("alfur", bcrypt_sha256.hash("alfur"), False)
db.session.add(admin)
db.session.add(siggi)
db.session.add(alfur)
db.session.commit()

admin_code = AdminCode(bcrypt_sha256.hash("Woof Woof"))
db.session.add(admin_code)
db.session.commit()
