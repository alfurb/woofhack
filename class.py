
s = """classification = db.Column(db.String(100))
submission_folder_path = db.Column(db.Text())
out = db.Column(db.Text())
test_type = db.Column(db.Text())"""
r = []
for i in s.splitlines():
    s, j = i.split(" = ")
    s = s.strip()
    r.append(s)
for i in r:
    print(i, end=", ")
print()
for i in r:
    print("self." + i + " = " + i)
