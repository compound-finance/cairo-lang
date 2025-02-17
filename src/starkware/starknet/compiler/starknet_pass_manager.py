from typing import Callable, Tuple

from starkware.cairo.lang.compiler.preprocessor.default_pass_manager import (
    ModuleCollector, default_pass_manager)
from starkware.cairo.lang.compiler.preprocessor.pass_manager import PassManager, VisitorStage
from starkware.starknet.compiler.starknet_preprocessor import StarknetPreprocessor
from starkware.starknet.compiler.storage_var import (
    StorageVarDeclVisitor, StorageVarImplentationVisitor)
from starkware.starknet.security.hints_whitelist import get_hints_whitelist


def starknet_pass_manager(
        prime: int, read_module: Callable[[str], Tuple[str, str]],
        opt_unused_functions: bool = True, disable_hint_validation: bool = False) -> PassManager:
    hint_whitelist = None if disable_hint_validation else get_hints_whitelist()
    manager = default_pass_manager(
        prime=prime, read_module=read_module, preprocessor_cls=StarknetPreprocessor,
        opt_unused_functions=opt_unused_functions,
        preprocessor_kwargs=dict(hint_whitelist=hint_whitelist))
    # Use ModuleCollector.additional_modules to import necessary modules, whose import line
    # may be added after the module_collector phase.
    manager.replace('module_collector', ModuleCollector(
        read_module=read_module,
        additional_modules=[
            'starkware.cairo.common.cairo_builtins',
            'starkware.cairo.common.hash',
            'starkware.starknet.core.storage.storage',
        ]))

    manager.add_before(
        existing_stage='identifier_collector',
        new_stage_name='storage_var_signature',
        new_stage=VisitorStage(StorageVarDeclVisitor, modify_ast=True))
    manager.add_after(
        existing_stage='struct_collector',
        new_stage_name='storage_var_implementation',
        new_stage=VisitorStage(StorageVarImplentationVisitor, modify_ast=True))
    return manager
