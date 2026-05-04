import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(order=True, frozen=True)
class GameDate:
    year: int
    month: int
    day: int

    @staticmethod
    def parse(date_str: str) -> "GameDate":
        parts = date_str.strip().split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid date format: {date_str}")
        return GameDate(int(parts[0]), int(parts[1]), int(parts[2]))

    def age_at(self, other: "GameDate") -> int:
        years = other.year - self.year
        if (other.month, other.day) < (self.month, self.day):
            years -= 1
        return years

    def __str__(self) -> str:
        return f"{self.year}.{self.month}.{self.day}"


@dataclass
class Character:
    char_id: int
    name: Optional[str] = None
    culture: Optional[str] = None
    religion: Optional[str] = None
    dynasty: Optional[int] = None
    father: Optional[int] = None
    mother: Optional[int] = None
    traits: List[str] = field(default_factory=list)
    birth: Optional[GameDate] = None
    death: Optional[GameDate] = None


def strip_comments(text: str) -> str:
    """
    Remove # comments, preserving # inside quoted strings.
    """
    result = []
    in_quotes = False
    i = 0

    while i < len(text):
        ch = text[i]

        if ch == '"':
            in_quotes = not in_quotes
            result.append(ch)
            i += 1
            continue

        if ch == "#" and not in_quotes:
            while i < len(text) and text[i] != "\n":
                i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def extract_blocks(text: str) -> Dict[int, str]:
    """
    Extract top-level character blocks from uncommented text.
    """
    blocks = {}
    i = 0
    n = len(text)
    header_pattern = re.compile(r'(\d+)\s*=\s*\{', re.MULTILINE)

    while i < n:
        match = header_pattern.search(text, i)
        if not match:
            break

        char_id = int(match.group(1))
        block_start = match.end() - 1  # points to "{"
        depth = 0
        j = block_start

        while j < n:
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    blocks[char_id] = text[match.start():j + 1]
                    i = j + 1
                    break
            j += 1
        else:
            raise ValueError(f"Unclosed block for character {char_id}")

    return blocks


def parse_character(char_id: int, block: str) -> Character:
    character = Character(char_id=char_id)

    def search(pattern: str) -> Optional[str]:
        m = re.search(pattern, block, re.MULTILINE)
        return m.group(1) if m else None

    character.name = search(r'\bname\s*=\s*"([^"]+)"')
    character.culture = search(r'\bculture\s*=\s*([^\s{}"]+)')
    character.religion = search(r'\breligion\s*=\s*([^\s{}"]+)')

    dynasty = search(r'\bdynasty\s*=\s*(\d+)')
    father = search(r'\bfather\s*=\s*(\d+)')
    mother = search(r'\bmother\s*=\s*(\d+)')

    character.dynasty = int(dynasty) if dynasty else None
    character.father = int(father) if father else None
    character.mother = int(mother) if mother else None

    character.traits = re.findall(r'\badd_trait\s*=\s*"([^"]+)"', block)

    birth_match = re.search(
        r'(\d+\.\d+\.\d+)\s*=\s*\{\s*birth\s*=\s*yes\s*\}',
        block,
        re.MULTILINE
    )
    death_match = re.search(
        r'(\d+\.\d+\.\d+)\s*=\s*\{\s*death\s*=\s*yes\s*\}',
        block,
        re.MULTILINE
    )

    if birth_match:
        character.birth = GameDate.parse(birth_match.group(1))
    if death_match:
        character.death = GameDate.parse(death_match.group(1))

    return character


def load_characters(filename: str) -> Dict[int, Character]:
    with open(filename, "r", encoding="cp1252") as f:
        raw_text = f.read()

    text = strip_comments(raw_text)
    blocks = extract_blocks(text)

    characters = {}
    for char_id, block in blocks.items():
        try:
            characters[char_id] = parse_character(char_id, block)
        except Exception as e:
            print(f"[PARSE ERROR] Character {char_id}: {e}")

    return characters


def has_twin_trait(character: Character) -> bool:
    return "twin" in character.traits


def has_creature_trait(character: Character) -> bool:
    return any("creature" in trait for trait in character.traits)


def get_display_name(character: Character) -> str:
    if character.name:
        return f'{character.char_id} ("{character.name}")'
    return str(character.char_id)


def check_same_year_siblings(characters: Dict[int, Character]) -> List[str]:
    issues = []
    parent_groups: Dict[Tuple[str, int], List[Character]] = {}

    for char in characters.values():
        if char.father is not None:
            parent_groups.setdefault(("father", char.father), []).append(char)
        if char.mother is not None:
            parent_groups.setdefault(("mother", char.mother), []).append(char)

    seen_pairs = set()

    for siblings in parent_groups.values():
        for i in range(len(siblings)):
            for j in range(i + 1, len(siblings)):
                a = siblings[i]
                b = siblings[j]

                if a.birth is None or b.birth is None:
                    continue

                if a.birth.year == b.birth.year:
                    if not has_twin_trait(a) and not has_twin_trait(b):
                        pair_key = tuple(sorted((a.char_id, b.char_id)))
                        if pair_key not in seen_pairs:
                            seen_pairs.add(pair_key)
                            issues.append(
                                f'[SAME-YEAR SIBLINGS WITHOUT TWIN] '
                                f'{get_display_name(a)} and {get_display_name(b)} '
                                f'were both born in {a.birth.year} and share a parent, '
                                f'but neither has trait "twin".'
                            )

    return issues


def check_creature_trait(characters: Dict[int, Character]) -> List[str]:
    issues = []
    for char in characters.values():
        if not has_creature_trait(char):
            issues.append(
                f'[MISSING CREATURE TRAIT] {get_display_name(char)} has no trait containing "creature".'
            )
    return issues


def check_dynasty_vs_parents(characters: Dict[int, Character]) -> List[str]:
    issues = []

    for char in characters.values():
        if char.dynasty is None:
            continue

        father = characters.get(char.father) if char.father is not None else None
        mother = characters.get(char.mother) if char.mother is not None else None

        # No parents recorded -> do not run this check
        if father is None and mother is None:
            continue

        shares_with_father = (
            father is not None and
            father.dynasty is not None and
            father.dynasty == char.dynasty
        )
        shares_with_mother = (
            mother is not None and
            mother.dynasty is not None and
            mother.dynasty == char.dynasty
        )

        if not shares_with_father and not shares_with_mother:
            issues.append(
                f'[DYNASTY MISMATCH] {get_display_name(char)} has dynasty {char.dynasty} '
                f'but shares it with neither recorded parent.'
            )

    return issues


def check_birth_after_parent_death(characters: Dict[int, Character]) -> List[str]:
    issues = []

    for char in characters.values():
        if char.birth is None:
            continue

        if char.father is not None and char.father in characters:
            father = characters[char.father]
            if father.death is not None and char.birth > father.death:
                issues.append(
                    f'[BORN AFTER FATHER DIED] {get_display_name(char)} was born on {char.birth}, '
                    f'after father {get_display_name(father)} died on {father.death}.'
                )

        if char.mother is not None and char.mother in characters:
            mother = characters[char.mother]
            if mother.death is not None and char.birth > mother.death:
                issues.append(
                    f'[BORN AFTER MOTHER DIED] {get_display_name(char)} was born on {char.birth}, '
                    f'after mother {get_display_name(mother)} died on {mother.death}.'
                )

    return issues


def check_birth_before_parent_birth(characters: Dict[int, Character]) -> List[str]:
    issues = []

    for char in characters.values():
        if char.birth is None:
            continue

        if char.father is not None and char.father in characters:
            father = characters[char.father]
            if father.birth is not None and char.birth < father.birth:
                issues.append(
                    f'[BORN BEFORE FATHER WAS BORN] {get_display_name(char)} was born on {char.birth}, '
                    f'before father {get_display_name(father)} was born on {father.birth}.'
                )

        if char.mother is not None and char.mother in characters:
            mother = characters[char.mother]
            if mother.birth is not None and char.birth < mother.birth:
                issues.append(
                    f'[BORN BEFORE MOTHER WAS BORN] {get_display_name(char)} was born on {char.birth}, '
                    f'before mother {get_display_name(mother)} was born on {mother.birth}.'
                )

    return issues


def check_father_too_young(characters: Dict[int, Character]) -> List[str]:
    issues = []

    for char in characters.values():
        if char.birth is None or char.father is None or char.father not in characters:
            continue

        father = characters[char.father]
        if father.birth is None:
            continue

        age = father.birth.age_at(char.birth)
        if age < 16:
            issues.append(
                f'[FATHER TOO YOUNG] {get_display_name(char)} was born on {char.birth} '
                f'when father {get_display_name(father)} was {age}.'
            )

    return issues


def check_mother_age(characters: Dict[int, Character]) -> List[str]:
    issues = []

    for char in characters.values():
        if char.birth is None or char.mother is None or char.mother not in characters:
            continue

        mother = characters[char.mother]
        if mother.birth is None:
            continue

        age = mother.birth.age_at(char.birth)

        if age < 16:
            issues.append(
                f'[MOTHER TOO YOUNG] {get_display_name(char)} was born on {char.birth} '
                f'when mother {get_display_name(mother)} was {age}.'
            )
        elif age > 42:
            issues.append(
                f'[MOTHER TOO OLD] {get_display_name(char)} was born on {char.birth} '
                f'when mother {get_display_name(mother)} was {age}.'
            )

    return issues


def main():
    if len(sys.argv) != 2:
        print("Usage: python check_characters.py characters.txt")
        sys.exit(1)

    filename = sys.argv[1]
    characters = load_characters(filename)

    all_issues = []
    all_issues.extend(check_same_year_siblings(characters))
    all_issues.extend(check_creature_trait(characters))
    all_issues.extend(check_dynasty_vs_parents(characters))
    all_issues.extend(check_birth_after_parent_death(characters))
    all_issues.extend(check_birth_before_parent_birth(characters))
    all_issues.extend(check_father_too_young(characters))
    all_issues.extend(check_mother_age(characters))

    if not all_issues:
        print("No issues found.")
        return

    for issue in all_issues:
        print(issue)

    print(f"\nTotal issues found: {len(all_issues)}")


if __name__ == "__main__":
    main()
