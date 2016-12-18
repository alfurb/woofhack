import random
import json
import os

filename = "examples/example.json"
no_examples = 10
no_test_cases = 100

input_generator = lambda: (random.randint(-10000, 10000), random.randint(-10000, 10000))
output_generator = lambda x: sum(x)


test_cases = []
for i in range(no_examples):
    case = dict()
    case["name"] = "example " + str(i)
    inp = input_generator()
    case["input"] = "\n".join(map(str, inp))
    case["output"] = str(output_generator(inp))
    case["type"] = "example"
    test_cases.append(case)

for i in range(no_test_cases):
    case = dict()
    case["name"] = "test " + str(i)
    inp = input_generator()
    case["input"] = "\n".join(map(str, inp))
    case["output"] = str(output_generator(inp))
    case["type"] = "test"
    test_cases.append(case)


with open(filename, 'w') as outfile:
    json.dump(test_cases, outfile)

