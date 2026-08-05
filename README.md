# foundry-invariant-init

Scaffold a Foundry invariant test suite for any Solidity contract in one command. It parses your
contract with Slither and generates the handler and the invariant test, wired together, so you skip the
blank-canvas setup and go straight to writing the properties that matter.

It is the tool that generates the pattern from
[foundry-invariant-starter](https://github.com/hunterinvariants/foundry-invariant-starter).

## Why

Invariant testing is powerful and a pain to start. Every new contract means copying a template,
deleting the example, renaming files, and hand-wiring a handler with a bounded wrapper per function.
This does that mechanical part for you.

## Install

```
pipx install slither-analyzer
python3 foundry_invariant_init.py src/Vault.sol
```

(Slither needs a solc that can compile your contract. `solc-select` handles that.)

## Usage

```
foundry-invariant-init src/Vault.sol
foundry-invariant-init src/Vault.sol --name Vault --out test/invariant
```

## What it generates

For a contract `Vault`:

- **`test/invariant/VaultHandler.sol`** — a handler with five actors, a `useActor` modifier, and one
  bounded wrapper for every state-changing external or public function. Numeric arguments get a
  `bound()` line, payable functions get `vm.deal` plus a fuzzed `msgValue`, and there is a marked spot
  for your ghost variables.
- **`test/invariant/Vault.invariant.t.sol`** — deploys the contract and the handler, points the fuzzer
  at the handler with `targetContract`, and leaves you an empty `invariant_example` to replace.

## What it does not do

It scaffolds; it does not invent your invariants. You still write the ghost logic and the properties
that must always hold, because those are specific to your contract and are the part worth thinking
about. The tool removes the boilerplate, not the judgement.

Constructor arguments and non-numeric parameters are marked with `TODO` comments where you need to fill
them in.

## License

MIT.
