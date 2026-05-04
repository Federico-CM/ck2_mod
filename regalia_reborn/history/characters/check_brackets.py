from pathlib import Path


def read_file_safely(path: str) -> str:
    try:
        return Path(path).read_text(encoding="cp1252")
    except UnicodeDecodeError:
        return Path(path).read_text(encoding="latin-1")


def check_curly_braces(file_path: str) -> bool:
    text = read_file_safely(file_path)

    balance = 0
    line = 1
    col = 0

    in_string = False
    in_comment = False

    for ch in text:
        col += 1

        if ch == "\n":
            line += 1
            col = 0
            in_comment = False
            continue

        # Handle comments
        if ch == "#" and not in_string:
            in_comment = True

        if in_comment:
            continue

        # Handle strings
        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        # Count braces
        if ch == "{":
            balance += 1
        elif ch == "}":
            balance -= 1
            if balance < 0:
                print(f"Unmatched closing brace at line {line}, column {col}")
                return False

    if balance == 0:
        print("All curly brackets are balanced.")
        return True
    else:
        print(f"Unmatched opening brace(s): {balance}")
        return False


if __name__ == "__main__":
    check_curly_braces("characters.txt")
