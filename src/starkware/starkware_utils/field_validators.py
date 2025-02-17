import os
from typing import Callable, Dict, Iterable, List, Optional, TypeVar, Union

import marshmallow
import marshmallow.validate
from web3 import Web3

DNS_REGEX = r'^((?!-)[${}a-z0-9-]{1,63}(?<!-)\.)+([a-z]{2,6}[\.]{0,1})$'

T = TypeVar('T')
TypeKey = TypeVar('TypeKey')
TypeValue = TypeVar('TypeValue')

ValidatorType = Callable[[T], Union[T, bool]]


# Validators for public use in config dataclasses.

def validate_regex_match(
        field_name: str, *, regex: str, allow_none: bool, regex_description: str) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be a legal {regex_description}'.format(
        field_name=field_name, regex_description=regex_description)
    validate_regex = marshmallow.validate.Regexp(regex=regex, error=error_message)

    def validator(value):
        if value is None:
            if allow_none:
                return True

            raise marshmallow.exceptions.ValidationError(message=error_message.format(input=value))

        return validate_regex(value)

    return validator


def validate_dns(*, allow_none: bool) -> ValidatorType:
    return validate_regex_match(
        field_name='dns', regex=DNS_REGEX, allow_none=allow_none, regex_description='DNS label')


def validate_url(
        *, url_name: str, schemes: marshmallow.types.StrSequenceOrSet,
        require_full_url: bool) -> ValidatorType:
    error_message = (
        'Invalid {url_name} URL: {{input}}; '
        'must be a legal URL starting with {schemes}').format(
        url_name=url_name, schemes=','.join(schemes))
    return marshmallow.validate.URL(
        schemes=schemes, require_tld=require_full_url, error=error_message)


validate_gateway_url = validate_url(
    url_name='Gateway endpoint', schemes={'http', 'https'}, require_full_url=False)

validate_internal_url = validate_url(
    url_name='Internal Gateway endpoint', schemes={'http', 'https'}, require_full_url=False)

validate_node_endpoint = validate_url(
    url_name='Node endpoint', schemes={'http', 'https'}, require_full_url=False)


def validate_one_of(
        field_name: str, *, choices: Iterable, allow_none: bool = False) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; allowed values: {{choices}}'.format(
        field_name=field_name)
    one_of_validator = marshmallow.validate.OneOf(choices=choices, error=error_message)

    def validator(value):
        if allow_none and value is None:
            return True

        return one_of_validator(value)

    return validator


def validate_equal(field_name: str, *, allowed_value: T) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be: {{other}}'.format(
        field_name=field_name)
    return marshmallow.validate.Equal(comparable=allowed_value, error=error_message)


def validate_in_range(
        field_name, *, min_value: Optional[int] = None, max_value: Optional[int] = None,
        min_inclusive: bool = True, max_inclusive: bool = True,
        allow_none: bool = False, error_message: Optional[str] = None) -> ValidatorType:
    if error_message is None:
        range_string = (
            f'{"[" if min_inclusive else "("}'
            f'{"-inf" if min_value is None else min_value},'
            f'{"inf" if max_value is None else max_value}'
            f'{"]" if max_inclusive else ")"}')
        error_message = \
            'Invalid {field_name}: {{input}}; must be in the range {range_string}'.format(
                field_name=field_name, range_string=range_string)

    range_validator = marshmallow.validate.Range(
        min=min_value, max=max_value, min_inclusive=min_inclusive, max_inclusive=max_inclusive,
        error=error_message)

    def validator(value):
        if allow_none and value is None:
            return True

        return range_validator(value)

    return validator


def validate_positive(field_name: str, *, allow_none: bool = False) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be a positive value'.format(
        field_name=field_name)
    return validate_in_range(
        field_name=field_name, min_value=0, min_inclusive=False, allow_none=allow_none,
        error_message=error_message)


def validate_non_negative(field_name, *, allow_none=False):
    error_message = 'Invalid {field_name}: {{input}}; must be a non-negative value'.format(
        field_name=field_name)
    return validate_in_range(
        field_name=field_name, min_value=0, min_inclusive=True, allow_none=allow_none,
        error_message=error_message)


def validate_positive_or_infinity(field_name: str) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be positive -1 (for unlimited)'.format(
        field_name=field_name)

    def validator(value):
        if value <= 0 and value != -1:
            raise marshmallow.ValidationError(error_message.format(input=value))

        return True

    return validator


def validate_probability(field_name: str, *, allow_none: bool = False) -> ValidatorType:
    return validate_in_range(
        field_name=field_name, min_value=0, max_value=1, min_inclusive=True, max_inclusive=True,
        allow_none=allow_none)


def validate_public_key(field_name: str) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be a legal Ethereum address'.format(
        field_name=field_name)

    address_regex = r'^0x[a-fA-F0-9]{40}$'
    validate_address_regex = marshmallow.validate.Regexp(regex=address_regex, error=error_message)

    def validator(addresses: Union[str, List[str]]):
        if isinstance(addresses, str):
            addresses = [addresses]

        for address in addresses:
            validate_address_regex(address)

            if not Web3.isChecksumAddress(address):
                raise marshmallow.ValidationError(error_message.format(input=address))

        return True

    return validator


def validate_private_key(field_name: str) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be a legal Ethereum private key'.format(
        field_name=field_name)

    private_key_regex = r'^0x[a-fA-F0-9]{64}$'
    return marshmallow.validate.Regexp(regex=private_key_regex, error=error_message)


def validate_customer_id(field_name: str) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be an alphanumeric string'.format(
        field_name=field_name)
    return marshmallow.validate.Regexp(regex=r'^[A-Za-z0-9_-]+$', error=error_message)


def validate_absolute_linux_path(field_name: str, *, allow_none: bool) -> ValidatorType:
    error_message = 'Invalid {field_name}: {{input}}; must be a legal absolute Linux path'.format(
        field_name=field_name)

    def validator(value: str):
        if allow_none and value is None:
            return True

        if not os.path.isabs(value):
            raise marshmallow.ValidationError(error_message.format(input=value))

        return True

    return validator


validate_certificates_path = validate_absolute_linux_path('certificates_path', allow_none=True)


def validate_communication_params(*, url: str, certificates_path: Optional[str]):
    https_used = url.startswith('https')
    certs_used = certificates_path is not None

    if certs_used and not https_used:
        raise ValueError('Certificates should be used together with a HTTPS URL')


def validate_dict(
        field_name: str,
        *, key_validator: Optional[Callable[[str], Callable[[TypeKey], bool]]] = None,
        value_validator: Optional[Callable[[str], Callable[[TypeValue], bool]]] = None,
        allow_none: bool = False) -> Callable[[Dict[TypeKey, TypeValue]], bool]:
    """
    Returns a validator for a dictionary, that validates the keys according to key_validator, and
    the values according to value_validator.
    These validators should be methods that get the field name, and return the validator for that
    field. Set these validators to None to have empty validators, which will always return True.
    """
    def validator(dictionary: Dict[TypeKey, TypeValue]):
        nonlocal key_validator, value_validator
        if allow_none and dictionary is None:
            return True
        if key_validator is None:
            key_validator = (lambda name: lambda key: True)
        if value_validator is None:
            value_validator = (lambda name: lambda value: True)
        for key, value in dictionary.items():
            try:
                (key_validator(str(key)))(key)
                (value_validator(str(key)))(value)
            except Exception as e:
                raise type(e)(f'Dictionary {field_name} is not valid: ' + str(e))
        return True

    return validator


def validate_power_of_two(field_name: str) -> ValidatorType:
    """
    Return a validator for a number, that validates that the number is a power of 2.
    """
    error_message = 'Invalid {field_name}: {{input}}; must be a power of 2'.format(
        field_name=field_name)

    def validator(value):
        tmp_value = value
        while tmp_value > 1:
            if tmp_value % 2 == 1:
                break
            tmp_value = tmp_value // 2

        if tmp_value != 1:
            raise marshmallow.ValidationError(error_message.format(input=value))
        return True

    return validator
