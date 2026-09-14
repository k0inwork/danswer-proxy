#!/usr/bin/env python3
import json
import os
import sys


def _db_path():
    return os.environ.get("TODO_DB", "todos.json")


def _load():
    path = _db_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return []
        return data
    except (json.JSONDecodeError, OSError):
        return []


def _save(todos):
    path = _db_path()
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(todos, fh)


def _next_id(todos):
    used = {t["id"] for t in todos}
    i = 1
    while i in used:
        i += 1
    return i


def cmd_add(args):
    if not args:
        print('Usage: todo.py add "<text>"', file=sys.stderr)
        return 1
    text = " ".join(args)
    todos = _load()
    new_id = _next_id(todos)
    todos.append({"id": new_id, "text": text, "done": False})
    _save(todos)
    print("Added #" + str(new_id) + ": " + text)
    return 0


def cmd_list(args):
    todos = _load()
    if not todos:
        print("No todos.")
        return 0
    for t in todos:
        mark = "x" if t["done"] else " "
        print("#" + str(t["id"]) + " [" + mark + "] " + t["text"])
    return 0


def cmd_done(args):
    if not args:
        print("Usage: todo.py done <id>", file=sys.stderr)
        return 1
    first = args.pop(0)
    try:
        target_id = int(first)
    except ValueError:
        print("Error: invalid id '" + first + "'", file=sys.stderr)
        return 1
    todos = _load()
    for t in todos:
        if t["id"] == target_id:
            t["done"] = True
            _save(todos)
            print("Done #" + str(target_id))
            return 0
    print("Error: unknown id #" + str(target_id), file=sys.stderr)
    return 1


def cmd_rm(args):
    if not args:
        print("Usage: todo.py rm <id>", file=sys.stderr)
        return 1
    first = args.pop(0)
    try:
        target_id = int(first)
    except ValueError:
        print("Error: invalid id '" + first + "'", file=sys.stderr)
        return 1
    todos = _load()
    for i, t in enumerate(todos):
        if t["id"] == target_id:
            todos.pop(i)
            _save(todos)
            print("Removed #" + str(target_id))
            return 0
    print("Error: unknown id #" + str(target_id), file=sys.stderr)
    return 1


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "done": cmd_done,
    "rm": cmd_rm,
}

USAGE = "Usage: todo.py <add|list|done|rm> [args]"


def main():
    argv = sys.argv[1:]
    if not argv:
        print(USAGE, file=sys.stderr)
        return 1
    head = argv.pop(0)
    if head not in COMMANDS:
        print("Unknown command: " + head, file=sys.stderr)
        print(USAGE, file=sys.stderr)
        return 1
    return COMMANDS[head](argv)


if __name__ == "__main__":
    sys.exit(main())
