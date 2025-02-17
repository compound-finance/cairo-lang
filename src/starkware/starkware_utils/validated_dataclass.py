import dataclasses
import inspect
import random
import re
from typing import Any, ClassVar, Dict, Optional, Sequence, Tuple, Type, TypeVar

import marshmallow
import marshmallow.fields as mfields
import marshmallow_dataclass
import typeguard

from starkware.starkware_utils.serializable import StringSerializable
from starkware.starkware_utils.validated_fields import Field

TValidatedDataclass = TypeVar('TValidatedDataclass', bound='ValidatedDataclass')
TSerializableDataclass = TypeVar('TSerializableDataclass', bound='SerializableMarshmallowDataclass')
T = TypeVar('T')


def camel_to_snake_case(camel_case_name: str) -> str:
    """
    Converts a name with Capital first letters to lower case with '_' as separators.
    For example, CamelToSnakeCase -> camel_to_snake_case.
    """
    return (camel_case_name[0] + re.sub(r'([A-Z])', r'_\1', camel_case_name[1:])).lower()


class SerializableMarshmallowDataclass(StringSerializable):
    """
    Base class to classes decorated with marshmallow_dataclass.dataclass, implementing the
    Serializable interface.
    """

    class_name_prefix: ClassVar[bytes]
    Schema: ClassVar[Type[marshmallow.Schema]]

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)  # type: ignore[call-arg]

        cls.class_name_prefix = camel_to_snake_case(camel_case_name=cls.__name__).encode('ascii')

    def dump(self) -> dict:
        return self.Schema().dump(obj=self)

    @classmethod
    def load(cls: Type[TSerializableDataclass], data: dict) -> TSerializableDataclass:
        return cls.Schema().load(data=data)

    def dumps(self) -> str:
        return self.Schema().dumps(obj=self)

    @classmethod
    def loads(cls: Type[TSerializableDataclass], data: str) -> TSerializableDataclass:
        return cls.Schema().loads(json_data=data)

    @classmethod
    def prefix(cls) -> bytes:
        """
        Converts the class name to a lower case name with '_' as separators and returns the
        bytes version of this name. For example HelloWorldAB -> b'hello_world_a_b'.
        """
        return cls.class_name_prefix


class ValidatedDataclass:
    """
    A class containing a type- and value-level validation.
    """

    def __post_init__(self):
        self.validate_dataclass()

    def validate_dataclass(self):
        self.validate_types()
        self.validate_values()

    @classmethod
    def get_random_element(
            cls: Type[TValidatedDataclass],
            random_object: Optional[random.Random] = None, **data) -> TValidatedDataclass:
        """
        Generates a random object of the given class restricted by the given data.
        Any field can be either passed as an argument (field_name=field_value), and if not,
        it is generated randomly.
        The random generation is done via the validated_field inside the metadata, or if there
        is no such and the field is a ValidatedMarshmallow class, it recursively uses
        get_random_element.

        Example usage:
            @marshmallow_dataclasses.dataclass
            class Inner(ValidatedMarshmallowDataclass):
                a: int = field(validated_field=...)
                b: int = field(validated_field=...)

            @marshmallow_dataclasses.dataclass
            class Outer(ValidatedMarshmallowDataclass):
                c: int = field(validated_field=...)
                d: int = field(validated_field=...)
                inner: Inner

            Outer.get_random_element(c=5)    # Randomize a, b and d.
        """
        new_object_data = {}
        for field in dataclasses.fields(cls):
            # Fields with a value from the arguments.
            if field.name in data.keys():
                new_object_data[field.name] = data[field.name]
                continue

            # Fields without a value from the arguments.
            validated_field = get_validated_field(field=field)
            if validated_field is not None:
                new_object_data[field.name] = validated_field.get_random_value(
                    random_object=random_object)
                continue

            # The field is a validated class object.
            is_validated_dataclass = (
                inspect.isclass(field.type) and
                issubclass(field.type, ValidatedMarshmallowDataclass))
            if is_validated_dataclass:
                new_object_data[field.name] = field.type.get_random_element(
                    random_object=random_object)
                continue

            raise Exception(
                f'Could not randomize the field {field.name} in an object of type {cls}.')

        return cls(**new_object_data)  # type: ignore

    def validate_values(self):
        for field in dataclasses.fields(self):
            metadata = getattr(field, 'metadata', None)
            if metadata is None:
                continue

            value = getattr(self, field.name)
            # First use the field_validated argument, and only if it does not exist,
            # use the validation inside the marshmallow field argument.
            validated_field = metadata.get('validated_field', None)
            if validated_field is None:
                marshmallow_field = field.metadata.get('marshmallow_field', None)
                if marshmallow_field is not None:
                    validate_field(field=marshmallow_field, value=value)
            else:
                name_in_messages = metadata.get('name_in_messages', None)
                validated_field.validate(value=value, name=name_in_messages)

    def validate_types(self):
        for field in dataclasses.fields(self):
            typeguard.check_type(
                argname=field.name, value=getattr(self, field.name), expected_type=field.type)


class ValidatedMarshmallowDataclass(ValidatedDataclass, SerializableMarshmallowDataclass):
    """
    Base class to classes decorated with marshmallow_dataclass.dataclass, containing validations.
    """


def get_validated_field(field: dataclasses.Field) -> Optional[Field]:
    """
    Checks if the dataclass field has a validated_field attribute in its metadata.
    If so returns it, otherwise returns None.
    """
    if field.metadata is not None and 'validated_field' in field.metadata:
        return field.metadata['validated_field']
    return None


def late_marshmallow_dataclass(cls: Optional[type] = None, **kwargs):
    """
    A helper function for creating marshmallow dataclasses while inheriting fields from base class.

    Example usage:
        class Base:
            x: T
            y: int = 5

        @marshmallow_dataclasses.dataclass
        class Child(Base):
            x: str
            # y: int = 5 will be inherited from parent, due to late_marshmallow_dataclass.

    Note that no parent class of the annotated class should be a dataclass.
    In case that a nondefault attribute follows a default attribute, it is not guaranteed that the
    derived class construction will work as expected.
    """
    if cls is None:  # Arguments passed directly to decorator.
        def inner(cls):
            prepare_class_annotations_and_attribute_values(cls)
            return marshmallow_dataclass.dataclass(cls, **kwargs)

        return inner

    prepare_class_annotations_and_attribute_values(cls)
    return marshmallow_dataclass.dataclass(cls)


def prepare_class_annotations_and_attribute_values(cls):
    """
    Prepares class annotations in the following manner:
    Annotations are added to __annotations__ dictionary in the reverse MRO order. Members with
    default values are added last, in order for them to appear last in the auto-generated __init__
    signature.
    In addition, sets values for attributes in cls.__dict__.
    """
    annotations, attr_values = process_class_annotations_and_attribute_values(cls=cls)
    set_class_annotations_and_attribute_values(
        cls=cls, annotations=annotations, attr_values=attr_values)


def process_class_annotations_and_attribute_values(cls) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns class attributes annotations and values.
    The annotations and values are taken from the first class the attribute appears in its
    annotations, in the cls' MRO order.
    """
    annotations: Dict[str, Any] = {}
    attr_values: Dict[str, Any] = {}

    for base_cls in inspect.getmro(cls):
        if '__annotations__' not in base_cls.__dict__:
            continue

        for name in base_cls.__annotations__:
            if name in annotations:
                # Attribute already seen in a derived class.
                continue

            if name in base_cls.__dict__:
                attr_values[name] = base_cls.__dict__[name]
                continue

            if ('__dataclass_fields__' in base_cls.__dict__ and
                    name in base_cls.__dict__['__dataclass_fields__']):
                # cls is a dataclass, in which all fields appear in cls.__dataclass_fields__,
                # rather than directly in cls.__dict__.
                attr_values[name] = base_cls.__dict__['__dataclass_fields__'][name]
                continue

        # Prepand annotations, so that they appear in reverse MRO order.
        annotations = {**base_cls.__annotations__, **annotations}

    return annotations, attr_values


def set_class_annotations_and_attribute_values(
        cls, annotations: Dict[str, Any], attr_values: Dict[str, Any]):
    """
    Sets given attributes to cls.__dict__ and its annotations.
    The annotations will contain the given annotations, where the attributes with default values
    will appear last.
    """
    # Make sure the attributes appear directly in cls.__dict__ as well.
    default_value_annotations: Dict[str, Any] = {}
    for name, attr_value in attr_values.items():
        setattr(cls, name, attr_value)

        if has_default_value(cls=cls, attr_value=attr_value):
            default_value_annotations[name] = annotations[name]

    # Locate members with default values in the end of the annotations dictionary.
    cls.__annotations__ = {
        name: annotation for name, annotation in annotations.items()
        if name not in default_value_annotations}
    cls.__annotations__.update(default_value_annotations)


def has_default_value(cls, attr_value: Any) -> bool:
    """
    Returns whether the class member has a default value or not.
    """
    if not isinstance(attr_value, dataclasses.Field):
        """
        Plain default value assignment:
            class A:
                x: int = 1
        """
        return True

    # If member does not appear in __init__'s signature, having a default value is irrelevant.
    return (
        attr_value.init and
        attr_value.default is not dataclasses.MISSING or
        # Mypy has a problem with object members that are callables (it sees access to them as
        # passing self). This is actually originated in dataclasses' annotations in typeshed, since
        # the source code has no annotations.
        # See https://github.com/python/mypy/issues/6910 for details on this problem.
        attr_value.default_factory is not dataclasses.MISSING)  # type: ignore


# Validators for private use in this file.

def validate_value(*, field: mfields.Field, value: Any):
    """
    Invokes the field's validator, if exists and it is callable.
    Note: multiple validators are not currently supported as an iterable, but rather as a single
    validation function that and-s between the validators' results.
    """
    if field.validate is not None and callable(field.validate):
        field.validate(value)


def validate_field(field: mfields.Field, value: Any):
    validate_value(field=field, value=value)

    # Validate inner elements, if field is a container.
    if isinstance(field, mfields.List):
        validate_list(field, value)
    elif isinstance(field, mfields.Mapping):
        if field.key_field is not None:
            validate_list(mfields.List(field.key_field), value.keys())
        if field.value_field is not None:
            validate_list(mfields.List(field.value_field), value.values())


def validate_list(list_field: mfields.List, list_value: Sequence):
    if not isinstance(list_field.inner, mfields.Field):
        # Nothing to check further, since it is not a marshmallow field.
        return

    if list_value is None:
        if list_field.allow_none:
            return

        raise marshmallow.ValidationError('Field may not be None.')

    for inner_element in list_value:
        validate_field(field=list_field.inner, value=inner_element)
