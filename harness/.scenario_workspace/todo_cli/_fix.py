import os, sys
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'todo.py')
with open(p) as f: src = f.read()
fixed = src
# Fix enumerate indent patterns (cmd_rm)
fixed = fixed.replace('for i, t in enumerate(todos):\n         if', 'for i, t in enumerate(todos):\n        if')
fixed = fixed.replace('for i, t in enumerate(todos):\n     if', 'for i, t in enumerate(todos):\n    if')
# Fix cmd_list: 5-space 'for t in todos:'
fixed = fixed.replace('    if not todos:\n        print("No todos.")\n        return 0\n     for t in todos:', '    if not todos:\n        print("No todos.")\n        return 0\n    for t in todos:')
# Fix main(): 9-space print(USAGE) inside 'if not argv:'
fixed = fixed.replace('    if not argv:\n         print(USAGE, file=sys.stderr)\n        return 1', '    if not argv:\n        print(USAGE, file=sys.stderr)\n        return 1')
if fixed == src:
    sys.exit(0)
with open(p, 'w') as f: f.write(fixed)
print('fixed')
