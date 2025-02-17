import os
from unittest.mock import MagicMock

import pytest

from starkware.cairo.common.cairo_function_runner import CairoFunctionRunner
from starkware.cairo.common.structs import CairoStructFactory, CairoStructProxy
from starkware.cairo.lang.cairo_constants import DEFAULT_PRIME
from starkware.cairo.lang.compiler.cairo_compile import compile_cairo_files
from starkware.cairo.lang.compiler.program import Program

CAIRO_FILE = os.path.join(os.path.dirname(__file__), 'storage.cairo')


@pytest.fixture
def program() -> Program:
    return compile_cairo_files([CAIRO_FILE], prime=DEFAULT_PRIME)


@pytest.fixture
def structs(program: Program) -> CairoStructProxy:
    return CairoStructFactory.from_program(program).structs


@pytest.fixture
def runner(program: Program) -> CairoFunctionRunner:
    return CairoFunctionRunner(program)


def test_storage_read(runner: CairoFunctionRunner, structs: CairoStructProxy):
    stark_net_storage = MagicMock(name='storage')

    storage_value = 45
    stark_net_storage.read.return_value = storage_value

    storage_ptr = runner.segments.add()
    address = 17

    runner.run(
        'storage_read', storage_ptr=storage_ptr, address=address,
        hint_locals={'__storage': stark_net_storage})

    storage_end, value = runner.get_return_values(2)
    assert value == storage_value
    assert runner.vm_memory.get_range(
        storage_ptr, storage_end - storage_ptr) == list(structs.DictAccess(
            key=address, prev_value=value, new_value=value))

    stark_net_storage.read.assert_called_once_with(address=address)


def test_storage_write(runner: CairoFunctionRunner, structs: CairoStructProxy):
    stark_net_storage = MagicMock(name='storage')

    orig_value = 45
    new_value = 42
    stark_net_storage.read.return_value = orig_value

    storage_ptr = runner.segments.add()
    address = 17

    runner.run(
        'storage_write', storage_ptr=storage_ptr, address=address, value=new_value,
        hint_locals={'__storage': stark_net_storage})

    storage_end, = runner.get_return_values(1)
    assert runner.vm_memory.get_range(
        storage_ptr, storage_end - storage_ptr) == list(structs.DictAccess(
            key=address, prev_value=orig_value, new_value=new_value))

    stark_net_storage.read.assert_called_once_with(address=address)
    stark_net_storage.write.assert_called_once_with(address=address, value=new_value)
