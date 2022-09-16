from inspect import Signature
from abc import ABC, abstractmethod


CLIENT_CONSTANT_METHODS = ['update_methods']
GET_METHODS_LIST_REQUEST = '__get_methods_list'
PRIVATE_OR_PROTECTED_PREFIX = '_'

# TODO: define following:
# __get_class_name,
# __get_class_help,
# __get_method_help,
# __update_server


class RelstClient(ABC):
    # NOTE: this name musn't be overriden by server methods
    def UPDATE_METHODS(self):
        self._remove_methods()
        methods_list_response = self._handle_request(GET_METHODS_LIST_REQUEST)

        # TODO: parse methods_list
        methods_list = methods_list_response

        for method in methods_list:
            self._add_method(**method)

    @abstractmethod
    def _handle_request(self, method_name: str, **method_args) -> dict:
        pass

    def _remove_methods(self):
        """
        :brief: method used to remove all public functions (except for exceptions)
        :remarks: note for the race condition (where attribute is deleted before delattr)
        """

        should_method_be_deleted = lambda first_letter: (
            first_letter!= PRIVATE_OR_PROTECTED_PREFIX
            and not first_letter.isupper()
        )

        for attribute_name in dir(self):
            if should_method_be_deleted(attribute_name[0]):
                delattr(self, attribute_name)

    def _add_method(self, method_name: str, method_signature: Signature):
        def method_caller(**kwargs):
            return self._handle_request(method_name, **kwargs)

        method_caller.__name__ = method_name
        method_caller.__annotations__ = method_signature.__annotations__

        setattr(self, method_name, method_caller)

    def __enter__(self):
        self.UPDATE_METHODS()

    def __exit__(self, exc_type, exc_value, traceback):
        pass
