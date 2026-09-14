# Todo CLI — Specification

Build a command-line todo application as a single Python 3 file named
`todo.py` in the workspace root. No third-party dependencies.

## Storage

- Todos are persisted as JSON in the file given by the `TODO_DB` environment
  variable. If `TODO_DB` is not set, use `todos.json` in the current working
  directory.
- JSON schema: a list of objects `{"id": <int>, "text": <str>, "done": <bool>}`.
- If the storage file does not exist, start with an empty list (do not crash).

## Commands

Run as `python3 todo.py <command> [args]`.

### `add "text"`
- Appends a new todo with `done = false`.
- Prints exactly: `Added #<id>: <text>`
- Exit code 0.
- Missing text argument: print usage to stderr, exit code 1.

### `list`
- Prints one line per todo, oldest first:
  - open: `#<id> [ ] <text>`
  - done: `#<id> [x] <text>`
- If there are no todos, prints exactly: `No todos.`
- Exit code 0.

### `done <id>`
- Marks the todo with the given id as done.
- Prints exactly: `Done #<id>`
- Unknown id: print an error to stderr, exit code 1.
- Exit code 0 on success.

### `rm <id>`
- Removes the todo with the given id.
- Prints exactly: `Removed #<id>`
- Unknown id: print an error to stderr, exit code 1.
- Exit code 0 on success.

## ID rules

- Ids are positive integers.
- A new todo gets the smallest positive integer id not currently in use
  (ids of removed todos are reused).

## General rules

- All other output (banners, logs, help text) must go to stderr or not exist;
  stdout of each command must contain exactly what the spec states
  (`list` prints only the todo lines, nothing else).
- Unknown commands: print usage to stderr, exit code 1.
- The program must never print a Python traceback for expected errors.
