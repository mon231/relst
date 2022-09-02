import string
import random
from types import FunctionType


FUNCTION_NAME_LENGTH = 8


class NameGenerator:
    def __init__(self):
        self.__used_names = {None}

    def rename_function(self, function: FunctionType):
        function.__name__ = self.__generate_name()
        return function

    def __generate_name(self) -> str:
        new_name = None

        while new_name in self.__used_names:
            new_name = ''.join(random.choices(string.ascii_uppercase, k=FUNCTION_NAME_LENGTH))

        self.__used_names.add(new_name)
        return new_name
