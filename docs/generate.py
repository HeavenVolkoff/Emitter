#!/usr/bin/env python3

# Internal
import typing as T
from types import ModuleType
from pathlib import Path

# External
import pdoc


def main(module_def: T.Union[ModuleType, str], **configs):
    def gen_submodules(mod, path=None):
        path = (path or Path()) / mod.name.replace(mod.supermodule.name, "").strip(". \n")
        submodules = mod.submodules()

        if submodules:
            path.mkdir()
            (path / "README.md").write_text(mod.text(**configs))
            for submodule in submodules:
                gen_submodules(submodule, path)
        else:
            path.with_suffix(".md").write_text(mod.text(**configs))

    context = pdoc.Context()
    module = pdoc.Module(module_def, context=context)

    pdoc.link_inheritance(context)

    Path("README.md").write_text(module.text(**configs))
    for submodule in module.submodules():
        gen_submodules(submodule)


if __name__ == "__main__":
    import emitter

    main(emitter, show_type_annotations=True)
