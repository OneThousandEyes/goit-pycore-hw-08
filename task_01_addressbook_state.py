from collections import UserDict
from datetime import datetime, date, timedelta
import re
import pickle
from colorama import init as colorama_init, Fore, Style
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory

colorama_init(autoreset=True)

# ===================== МОДЕЛІ ДАНИХ =====================

class Field:
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return str(self.value)


class Name(Field):
    def __init__(self, value: str):
        value = (value or "").strip()
        if not value:
            raise ValueError("Name cannot be empty")
        super().__init__(value)


class Phone(Field):
    """10 цифр, зберігаємо тільки цифри."""
    def __init__(self, value):
        digits = re.sub(r"\D", "", str(value))
        if len(digits) != 10:
            raise ValueError("Phone must contain exactly 10 digits")
        super().__init__(digits)


class Birthday(Field):
    """Формат DD.MM.YYYY, зберігаємо date, не з майбутнього."""
    def __init__(self, value):
        d = self._parse_birthday(value)
        if d > date.today():
            raise ValueError("Birthday cannot be in the future")
        self.value = d

    @staticmethod
    def _parse_birthday(value) -> date:
        """Окремий метод для парсингу та базової валідації формату."""
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            try:
                return datetime.strptime(value.strip(), "%d.%m.%Y").date()
            except ValueError:
                raise ValueError("Invalid date format. Use DD.MM.YYYY")
        raise ValueError("Invalid date format. Use DD.MM.YYYY")

    def __str__(self):
        return self.value.strftime("%d.%m.%Y")


class Record:
    """Одна картка контакту. Містить Name, список Phone, необов'язково Birthday."""
    def __init__(self, name: str):
        self.name = Name(name)
        self.phones: list[Phone] = []
        self.birthday: Birthday | None = None

    def add_phone(self, phone: str):
        p = Phone(phone)
        if not any(existing.value == p.value for existing in self.phones):
            self.phones.append(p)

    def find_phone(self, phone: str):
        digits = re.sub(r"\D", "", str(phone))
        for p in self.phones:
            if p.value == digits:
                return p
        return None

    def remove_phone(self, phone: str) -> bool:
        target = self.find_phone(phone)
        if target:
            self.phones.remove(target)
            return True
        return False

    def edit_phone(self, phone_old: str, phone_new: str) -> bool:
        old_digits = re.sub(r"\D", "", str(phone_old))
        new_p = Phone(phone_new)
        for i, p in enumerate(self.phones):
            if p.value == old_digits:
                if any(x.value == new_p.value for x in self.phones):
                    self.phones.pop(i)
                    return True
                self.phones[i] = new_p
                return True
        return False

    def add_birthday(self, birthday: str | date | datetime):
        if self.birthday is not None:
            raise ValueError("Birthday is already set for this contact")
        self.birthday = Birthday(birthday)

    def __str__(self):
        phones_str = "; ".join(p.value for p in self.phones) if self.phones else "-"
        bday_str = str(self.birthday) if self.birthday else "-"

        return (
            f"{Fore.CYAN}Contact name: {Fore.YELLOW}{self.name.value}{Style.RESET_ALL},\n"
            f"{Fore.CYAN}phones: {Fore.GREEN}{phones_str}{Style.RESET_ALL},\n"
            f"{Fore.CYAN}birthday: {Fore.MAGENTA}{bday_str}{Style.RESET_ALL}"
        )


class AddressBook(UserDict):
    """Колекція записів контактів."""
    def add_record(self, record: Record) -> None:
        self.data[record.name.value] = record

    def find(self, name: str):
        return self.data.get(name)

    def delete(self, name: str) -> bool:
        if name in self.data:
            del self.data[name]
            return True
        return False

    def get_upcoming_birthdays(self) -> list[dict]:
        """
        Повертає список словників:
        {"name": <ім'я>, "congratulation_date": "DD.MM.YYYY"}
        для ДН у найближчі 7 днів. Вітання з вихідних переносимо на понеділок.
        """
        today = date.today()
        result = []

        for record in self.data.values():
            if not record.birthday:
                continue
            bday: date = record.birthday.value

            candidate = date(today.year, bday.month, bday.day)
            if candidate < today:
                candidate = date(today.year + 1, bday.month, bday.day)

            delta_days = (candidate - today).days
            if 0 <= delta_days < 7:
                congrats = candidate
                if congrats.weekday() >= 5:  # 5=субота, 6=неділя
                    congrats += timedelta(days=(7 - congrats.weekday()))
                result.append({
                    "name": record.name.value,
                    "congratulation_date": congrats.strftime("%d.%m.%Y")
                })

        return sorted(
            result,
            key=lambda x: datetime.strptime(x["congratulation_date"], "%d.%m.%Y").date()
        )


# ===================== ЗБЕРЕЖЕННЯ / ЗАВАНТАЖЕННЯ (pickle) =====================

def save_data(book: AddressBook, filename: str = "addressbook.pkl"):
    """Серіалізація AddressBook у файл."""
    with open(filename, "wb") as f:
        pickle.dump(book, f)


def load_data(filename: str = "addressbook.pkl") -> AddressBook:
    """Десеріалізація AddressBook з файлу або створення нової, якщо файлу немає."""
    try:
        with open(filename, "rb") as f:
            return pickle.load(f)
    except FileNotFoundError:
        return AddressBook()


# ===================== ДЕКОРАТОР ТА ХЕНДЛЕРИ =====================

def input_error(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IndexError:
            return Fore.RED + "Недостатньо аргументів для цієї команди." + Style.RESET_ALL
        except KeyError as e:
            return Fore.RED + f"Не знайдено: {e}" + Style.RESET_ALL
        except ValueError as e:
            return Fore.RED + str(e) + Style.RESET_ALL
        except Exception as e:
            return Fore.RED + f"Сталася помилка: {e}" + Style.RESET_ALL
    return wrapper


@input_error
def add_contact(args, book: AddressBook):
    """add [ім'я] [телефон]"""
    msg = need("add", args, 2)
    if msg:
        return msg
    name, phone, *_ = args
    record = book.find(name)
    message = Fore.YELLOW + "Contact updated." + Style.RESET_ALL
    if record is None:
        record = Record(name)
        book.add_record(record)
        message = Fore.GREEN + "Contact added." + Style.RESET_ALL
    if phone:
        record.add_phone(phone)
    return message


@input_error
def change(args, book: AddressBook):
    """change [ім'я] [старий] [новий]"""
    msg = need("change", args, 3)
    if msg:
        return msg
    name, old, new = args[0], args[1], args[2]
    rec = book.find(name)
    if rec is None:
        return Fore.RED + "Контакт не знайдено." + Style.RESET_ALL
    if rec.edit_phone(old, new):
        return Fore.GREEN + "Номер змінено." + Style.RESET_ALL
    return Fore.RED + "Старий номер не знайдено." + Style.RESET_ALL


@input_error
def phone(args, book: AddressBook):
    """phone [ім'я]"""
    msg = need("phone", args, 1)
    if msg:
        return msg
    name = args[0]
    rec = book.find(name)
    if rec is None:
        return Fore.RED + "Контакт не знайдено." + Style.RESET_ALL
    if not rec.phones:
        return Fore.YELLOW + "У контакта немає телефонів." + Style.RESET_ALL
    return Fore.GREEN + ", ".join(p.value for p in rec.phones) + Style.RESET_ALL


@input_error
def show_all(args, book: AddressBook):
    msg = need("all", args, 0)
    if msg:
        return msg
    if not book.data:
        return Fore.YELLOW + "Адресна книга порожня." + Style.RESET_ALL
    lines = []
    for rec in book.data.values():
        lines.append(str(rec))
    return "\n\n".join(lines)


@input_error
def add_birthday(args, book: AddressBook):
    """add-birthday [ім'я] [DD.MM.YYYY]"""
    msg = need("add-birthday", args, 2)
    if msg:
        return msg
    name, bday = args[0], args[1]
    rec = book.find(name)
    if rec is None:
        return (
            Fore.RED
            + "Контакт не знайдено. Спочатку додайте контакт командою: add [ім'я] [телефон]"
            + Style.RESET_ALL
        )
    rec.add_birthday(bday)
    return Fore.GREEN + f"День народження для {name} додано." + Style.RESET_ALL


@input_error
def show_birthday(args, book: AddressBook):
    """show-birthday [ім'я]"""
    msg = need("show-birthday", args, 1)
    if msg:
        return msg
    name = args[0]
    rec = book.find(name)
    if rec is None:
        return Fore.RED + "Контакт не знайдено." + Style.RESET_ALL
    if not rec.birthday:
        return Fore.YELLOW + "День народження не встановлено." + Style.RESET_ALL
    return Fore.GREEN + str(rec.birthday) + Style.RESET_ALL


@input_error
def birthdays(args, book: AddressBook):
    """birthdays найближчим тижнем"""
    msg = need("birthdays", args, 0)
    if msg:
        return msg
    schedule = book.get_upcoming_birthdays()
    if not schedule:
        return Fore.YELLOW + "Найближчого тижня немає днів народження." + Style.RESET_ALL
    # згрупуємо по даті
    by_date = {}
    for item in schedule:
        by_date.setdefault(item["congratulation_date"], []).append(item["name"])
    lines = []
    for d in sorted(by_date, key=lambda s: datetime.strptime(s, "%d.%m.%Y").date()):
        lines.append(
            f"{Fore.CYAN}{d}:{Style.RESET_ALL} {Fore.GREEN}{', '.join(by_date[d])}{Style.RESET_ALL}"
        )
    return "\n".join(lines)


def hello(args, book):
    return Fore.CYAN + "Вітаю! Чим можу допомогти?" + Style.RESET_ALL


def exit_cmd(args, book):
    return Fore.CYAN + "До зустрічі!" + Style.RESET_ALL


# ===== ПІДКАЗКИ ДЛЯ КОМАНД =====
USAGE = {
    "add": "Використання: add <ім'я> <телефон>\nПриклад: add John 0931234567",
    "change": "Використання: change <ім'я> <старий_телефон> <новий_телефон>\nПриклад: change John 0931234567 0501112233",
    "phone": "Використання: phone <ім'я>\nПриклад: phone John",
    "all": "Використання: all",
    "add-birthday": "Використання: add-birthday <ім'я> <DD.MM.YYYY>\nПриклад: add-birthday John 15.08.1992",
    "show-birthday": "Використання: show-birthday <ім'я>\nПриклад: show-birthday John",
    "birthdays": "Використання: birthdays",
    "hello": "Використання: hello",
    "close": "Використання: close",
    "exit": "Використання: exit",
}


def need(cmd: str, args: list, n_required: int):
    """Повертає текст підказки, якщо аргументів менше ніж потрібно."""
    if len(args) < n_required:
        return (
            Fore.RED
            + "Недостатньо аргументів.\n"
            + USAGE.get(cmd, "Немає підказки для цієї команди.")
            + Style.RESET_ALL
        )
    return None


# ===================== ПАРСИНГ ТА ГОЛОВНИЙ ЦИКЛ =====================

COMMANDS = {
    "hello": hello,
    "add": add_contact,
    "change": change,
    "phone": phone,
    "all": show_all,
    "add-birthday": add_birthday,
    "show-birthday": show_birthday,
    "birthdays": birthdays,
    "close": exit_cmd,
    "exit": exit_cmd,
}

NAME_ARG_COMMANDS = {"add", "change", "phone", "add-birthday", "show-birthday"}

def parse_command(line: str):
    parts = line.strip().split()
    if not parts:
        return None, []
    cmd = parts[0].lower()
    args = parts[1:]
    return cmd, args


# ===== AUTOCOMPLETE via prompt_toolkit =====

class BotCompleter(Completer):
    def __init__(self, book: AddressBook):
        self.book = book

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        stripped = text.lstrip()
        words = stripped.split()

        if not words:
            # нічого не введено — показуємо всі команди
            options = sorted(COMMANDS.keys())
            prefix = ""
        else:
            current_word = document.get_word_under_cursor() or ""
            cmd = words[0].lower()
            ends_with_space = stripped.endswith(" ")

            # визначаємо індекс "поточного" слова
            if ends_with_space:
                # курсор одразу після пробілу -> нове слово
                word_index = len(words)
            else:
                word_index = len(words) - 1

            if word_index == 0:
                # перше слово → команди
                options = COMMANDS.keys()
                prefix = current_word

            elif word_index == 1:
                # друге слово:
                # тільки для команд, що приймають ім'я
                if cmd in NAME_ARG_COMMANDS:
                    options = self.book.data.keys()
                else:
                    options = []
                prefix = current_word

            else:
                # третє і далі — нічого не підказуємо
                options = []
                prefix = current_word

        for opt in sorted(set(options)):
            if opt.startswith(prefix):
                yield Completion(opt, start_position=-len(prefix))


def print_banner():
    print(
        f"{Fore.CYAN}{Style.BRIGHT}"
        "=============================================\n"
        "            [📒 Адресна книга]\n"
        "=============================================\n"
        "Доступні команди: \n"
        "hello, add, change, phone, \nall, add-birthday, show-birthday, \n"
        "birthdays, close, exit\n"
        "============================================="
        f"{Style.RESET_ALL}"
    )
    print(
        f"{Fore.MAGENTA}"
        "Підказка: використовуйте Tab для автодоповнення."
        f"{Style.RESET_ALL}"
    )

def main():
    book = load_data()

    completer = BotCompleter(book)
    session = PromptSession(
        history=InMemoryHistory(),
        completer=completer,
    )

    print_banner()

    while True:
        try:
            line = session.prompt("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            print(exit_cmd([], book))
            save_data(book)
            break

        cmd, args = parse_command(line)
        if not cmd:
            continue
        handler = COMMANDS.get(cmd)
        if not handler:
            print(
                Fore.RED
                + "Невідома команда.\nМожливі команди: "
                + ", ".join(COMMANDS.keys())
                + Style.RESET_ALL
            )
            continue

        result = handler(args, book)
        print(result)
        if handler is exit_cmd:
            save_data(book)
            break


if __name__ == "__main__":
    main()
