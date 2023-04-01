"""
New tests for v2 of serialization logic.
"""
from typing import Any, Optional

import pytest
from pydantic_core import PydanticSerializationError, core_schema
from typing_extensions import Annotated

from pydantic import (
    BaseModel,
    FieldSerializationInfo,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_serializer,
)


def test_serialize_decorator_always():
    class MyModel(BaseModel):
        x: Optional[int]

        @field_serializer('x', json_return_type='str')
        def customise_x_serialisation(v, _info):
            return f'{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': '1,234'}
    assert MyModel(x=1234).model_dump(mode='json') == {'x': '1,234'}
    assert MyModel(x=1234).model_dump_json() == '{"x":"1,234"}'
    m = MyModel(x=None)
    # can't use v:, on None, hence error
    error_msg = (
        'Error calling function `customise_x_serialisation`: '
        'TypeError: unsupported format string passed to NoneType.__format__'
    )
    with pytest.raises(PydanticSerializationError, match=error_msg):
        m.model_dump()
    with pytest.raises(PydanticSerializationError, match=error_msg):
        m.model_dump_json()


def test_serialize_decorator_json():
    class MyModel(BaseModel):
        x: int

        @field_serializer('x', json_return_type='str', when_used='json')
        def customise_x_serialisation(v, _info):
            return f'{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': 1234}
    assert MyModel(x=1234).model_dump(mode='json') == {'x': '1,234'}
    assert MyModel(x=1234).model_dump_json() == '{"x":"1,234"}'


def test_serialize_decorator_unless_none():
    class MyModel(BaseModel):
        x: Optional[int]

        @field_serializer('x', when_used='unless-none')
        def customise_x_serialisation(v, _info):
            return f'{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': '1,234'}
    assert MyModel(x=None).model_dump() == {'x': None}
    assert MyModel(x=1234).model_dump(mode='json') == {'x': '1,234'}
    assert MyModel(x=None).model_dump(mode='json') == {'x': None}
    assert MyModel(x=1234).model_dump_json() == '{"x":"1,234"}'
    assert MyModel(x=None).model_dump_json() == '{"x":null}'


def test_annotated_customisation():
    def parse_int(s: str, _: Any) -> int:
        return int(s.replace(',', ''))

    class CommaFriendlyIntLogic:
        @classmethod
        def __get_pydantic_core_schema__(cls, _schema):
            # here we ignore the schema argument (which is just `{'type': 'int'}`) and return our own
            return core_schema.general_before_validator_function(
                parse_int,
                core_schema.int_schema(),
                serialization=core_schema.format_ser_schema(',', when_used='unless-none'),
            )

    CommaFriendlyInt = Annotated[int, CommaFriendlyIntLogic]

    class MyModel(BaseModel):
        x: CommaFriendlyInt

    m = MyModel(x='1,000')
    assert m.x == 1000
    assert m.model_dump(mode='json') == {'x': '1,000'}
    assert m.model_dump_json() == '{"x":"1,000"}'


def test_serialize_valid_signatures():
    def ser_plain(v: Any, info: SerializationInfo) -> Any:
        return f'{v:,}'

    def ser_wrap(v: Any, nxt: SerializerFunctionWrapHandler, info: SerializationInfo) -> Any:
        return f'{nxt(v):,}'

    class MyModel(BaseModel):
        f1: int
        f2: int
        f3: int
        f4: int

        @field_serializer('f1')
        def ser_f1(self, v: Any, info: FieldSerializationInfo) -> Any:
            assert self.f1 == 1_000
            assert v == 1_000
            assert info.field_name == 'f1'
            return f'{v:,}'

        @field_serializer('f2', mode='wrap')
        def ser_f2(self, v: Any, nxt: SerializerFunctionWrapHandler, info: FieldSerializationInfo) -> Any:
            assert self.f2 == 2_000
            assert v == 2_000
            assert info.field_name == 'f2'
            return f'{nxt(v):,}'

        ser_f3 = field_serializer('f3')(ser_plain)
        ser_f4 = field_serializer('f4', mode='wrap')(ser_wrap)

    m = MyModel(**{f'f{x}': x * 1_000 for x in range(1, 9)})

    assert m.model_dump() == {
        'f1': '1,000',
        'f2': '2,000',
        'f3': '3,000',
        'f4': '4,000',
    }
    assert m.model_dump_json() == '{"f1":"1,000","f2":"2,000","f3":"3,000","f4":"4,000"}'


def test_invalid_signature_no_params() -> None:
    with pytest.raises(TypeError, match='Unrecognized serializer signature'):

        class _(BaseModel):
            x: int

            # caught by type checkers
            @field_serializer('x')
            def no_args() -> Any:  # pragma: no cover
                ...


def test_invalid_signature_single_params() -> None:
    with pytest.raises(TypeError, match='Unrecognized serializer signature'):

        class _(BaseModel):
            x: int

            # not caught by type checkers
            @field_serializer('x')
            def no_args(self) -> Any:  # pragma: no cover
                ...


def test_invalid_signature_too_many_params_1() -> None:
    with pytest.raises(TypeError, match='Unrecognized serializer signature'):

        class _(BaseModel):
            x: int

            # caught by type checkers
            @field_serializer('x')
            def no_args(self, value: Any, nxt: Any, info: Any, extra_param: Any) -> Any:  # pragma: no cover
                ...


def test_invalid_signature_too_many_params_2() -> None:
    with pytest.raises(TypeError, match='Unrecognized serializer signature'):

        class _(BaseModel):
            x: int

            # caught by type checkers
            @field_serializer('x')
            @staticmethod
            def no_args(not_self: Any, value: Any, nxt: Any, info: Any) -> Any:  # pragma: no cover
                ...


def test_invalid_signature_bad_plain_signature() -> None:
    with pytest.raises(TypeError, match='Unrecognized serializer signature for'):

        class _(BaseModel):
            x: int

            # caught by type checkers
            @field_serializer('x', mode='plain')
            def no_args(self, value: Any, nxt: Any, info: Any) -> Any:  # pragma: no cover
                ...


def test_serialize_ignore_info_plain():
    class MyModel(BaseModel):
        x: int

        @field_serializer('x')
        def ser_x(v: Any) -> str:
            return f'{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': '1,234'}


def test_serialize_ignore_info_wrap():
    class MyModel(BaseModel):
        x: int

        @field_serializer('x', mode='wrap')
        def ser_x(v: Any, handler: SerializerFunctionWrapHandler) -> str:
            return f'{handler(v):,}'

    assert MyModel(x=1234).model_dump() == {'x': '1,234'}


def test_serialize_decorator_self_info():
    class MyModel(BaseModel):
        x: Optional[int]

        @field_serializer('x', json_return_type='str')
        def customise_x_serialisation(self, v, info):
            return f'{info.mode}:{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': 'python:1,234'}
    assert MyModel(x=1234).model_dump(mode='foobar') == {'x': 'foobar:1,234'}


def test_serialize_decorator_self_no_info():
    class MyModel(BaseModel):
        x: Optional[int]

        @field_serializer('x', json_return_type='str')
        def customise_x_serialisation(self, v):
            return f'{v:,}'

    assert MyModel(x=1234).model_dump() == {'x': '1,234'}