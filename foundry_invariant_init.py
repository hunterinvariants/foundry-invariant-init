#!/usr/bin/env python3
"""
foundry-invariant-init  --  scaffold a Foundry invariant test suite for a Solidity contract.

Parses a contract with Slither, then generates:
  - a Handler of bounded wrappers (one per state-changing external/public function), and
  - an invariant test contract wired to that handler,
so you skip the blank-canvas setup and go straight to writing the properties that matter.

Usage:
    foundry-invariant-init src/Vault.sol
    foundry-invariant-init src/Vault.sol --name Vault --out test/invariant

Requires: slither-analyzer (pip install slither-analyzer) and a solc that can compile the contract.
"""

import argparse
import os
import sys

UINT_TYPES = {f"uint{8 * i}" for i in range(1, 33)} | {"uint"}


def load_slither(path):
    try:
        from slither import Slither
    except ImportError:
        sys.exit("error: slither is not installed. Run: pip install slither-analyzer")
    try:
        return Slither(path)
    except Exception as exc:
        sys.exit(f"error: slither could not compile {path}:\n{exc}")


def pick_contract(slither, name):
    if name:
        for c in slither.contracts:
            if c.name == name:
                return c
        sys.exit(f"error: no contract named '{name}' in the file")
    concrete = [
        c for c in (slither.contracts_derived or slither.contracts)
        if not c.is_interface and not c.is_library and not getattr(c, "is_abstract", False)
    ]
    if not concrete:
        sys.exit("error: no concrete contract to target (only interfaces/libraries/abstract found)")
    if len(concrete) > 1:
        names = ", ".join(c.name for c in concrete)
        sys.exit(f"error: multiple contracts found ({names}). Choose one with --name")
    return concrete[0]


def state_changing_functions(contract):
    funcs = []
    for f in contract.functions_entry_points:
        if f.is_constructor or f.is_fallback or f.is_receive:
            continue
        if f.view or f.pure:
            continue
        funcs.append(f)
    return funcs


def param_prep(ptype, pname):
    if ptype in UINT_TYPES:
        return [f"        {pname} = bound({pname}, 0, 1e24); // TODO: tighten this range for your contract"]
    if ptype == "address":
        return [f"        // TODO: map {pname} to one of the actors if it must be a real user"]
    return []


def render_handler(contract, funcs, import_path):
    name = contract.name
    out = [
        "// SPDX-License-Identifier: MIT",
        "pragma solidity ^0.8.24;",
        "",
        'import {Test} from "forge-std/Test.sol";',
        f'import {{{name}}} from "{import_path}";',
        "",
        f"/// @notice Auto-generated invariant handler for {name}.",
        "///         The fuzzer calls these bounded wrappers, so every call is a valid action instead of",
        "///         reverting noise. Add ghost variables and tighten the bounds to match your logic.",
        f"contract {name}Handler is Test {{",
        f"    {name} public target;",
        "    address[] internal actors;",
        "    address internal currentActor;",
        "",
        "    // TODO: add ghost variables here to track expected state independently of the contract.",
        "",
        f"    constructor({name} target_) {{",
        "        target = target_;",
        "        for (uint256 i = 0; i < 5; i++) {",
        '            actors.push(makeAddr(string(abi.encodePacked("actor", vm.toString(i)))));',
        "        }",
        "    }",
        "",
        "    modifier useActor(uint256 seed) {",
        "        currentActor = actors[seed % actors.length];",
        "        vm.startPrank(currentActor);",
        "        _;",
        "        vm.stopPrank();",
        "    }",
    ]

    seen = {}
    for f in funcs:
        seen[f.name] = seen.get(f.name, 0) + 1
        wrapper = f.name if seen[f.name] == 1 else f"{f.name}_{seen[f.name]}"

        params, preps, call_args = [], [], []
        for i, p in enumerate(f.parameters):
            ptype = str(p.type)
            pname = p.name or f"arg{i}"
            params.append(f"{ptype} {pname}")
            preps.extend(param_prep(ptype, pname))
            call_args.append(pname)

        extra_params, value_prefix = [], ""
        if f.payable:
            extra_params.append("uint256 msgValue")
            preps.insert(0, "        vm.deal(currentActor, msgValue);")
            preps.insert(0, "        msgValue = bound(msgValue, 0, 100 ether);")
            value_prefix = "{value: msgValue}"

        sig = ", ".join(["uint256 actorSeed"] + extra_params + params)
        out.append("")
        out.append(f"    function {wrapper}({sig}) external useActor(actorSeed) {{")
        out.extend(preps)
        out.append(f"        target.{f.name}{value_prefix}({', '.join(call_args)});")
        out.append("    }")

    out.append("}")
    out.append("")
    return "\n".join(out)


def render_invariant(contract, import_path):
    name = contract.name
    ctor = contract.constructor
    ctor_args = "/* TODO: constructor args */" if (ctor and ctor.parameters) else ""
    out = [
        "// SPDX-License-Identifier: MIT",
        "pragma solidity ^0.8.24;",
        "",
        'import {Test} from "forge-std/Test.sol";',
        f'import {{{name}}} from "{import_path}";',
        f'import {{{name}Handler}} from "./{name}Handler.sol";',
        "",
        f"contract {name}InvariantTest is Test {{",
        f"    {name} internal target;",
        f"    {name}Handler internal handler;",
        "",
        "    function setUp() public {",
        f"        target = new {name}({ctor_args});",
    ]
    if ctor_args:
        out.append("        // NOTE: this contract takes constructor arguments; fill them in above or it will not compile.")
    out += [
        f"        handler = new {name}Handler(target);",
        "        targetContract(address(handler));",
        "    }",
        "",
        "    /// TODO: replace with a real property that must ALWAYS hold, checked against a ghost variable.",
        "    function invariant_example() public {",
        "        // example: assertEq(target.totalSupply(), handler.ghost_sumBalances());",
        "    }",
        "}",
        "",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(prog="foundry-invariant-init", description="Scaffold a Foundry invariant suite.")
    ap.add_argument("contract", help="path to the .sol file")
    ap.add_argument("--name", help="contract name, if the file defines more than one")
    ap.add_argument("--out", default="test/invariant", help="output directory (default: test/invariant)")
    ap.add_argument("--force", action="store_true", help="overwrite existing generated files")
    args = ap.parse_args()

    if not os.path.isfile(args.contract):
        sys.exit(f"error: file not found: {args.contract}")

    slither = load_slither(args.contract)
    contract = pick_contract(slither, args.name)
    funcs = state_changing_functions(contract)
    if not funcs:
        sys.exit(f"error: {contract.name} has no state-changing external/public functions to fuzz")

    os.makedirs(args.out, exist_ok=True)
    import_path = os.path.relpath(args.contract, args.out).replace(os.sep, "/")

    handler_path = os.path.join(args.out, f"{contract.name}Handler.sol")
    invariant_path = os.path.join(args.out, f"{contract.name}.invariant.t.sol")
    for p in (handler_path, invariant_path):
        if os.path.exists(p) and not args.force:
            sys.exit(f"error: {p} already exists (use --force to overwrite)")

    with open(handler_path, "w") as fh:
        fh.write(render_handler(contract, funcs, import_path))
    with open(invariant_path, "w") as fh:
        fh.write(render_invariant(contract, import_path))

    print(f"Scaffolded an invariant suite for {contract.name}:")
    print(f"  {handler_path}   ({len(funcs)} bounded action(s))")
    print(f"  {invariant_path}")
    print()
    print("Next:")
    print("  1. Add ghost variables in the handler to track expected state.")
    print("  2. Write real invariant_* properties in the test (delete invariant_example).")
    print("  3. Ensure foundry.toml has an [invariant] block with fail_on_revert = true.")
    print("  4. forge test")


if __name__ == "__main__":
    main()
