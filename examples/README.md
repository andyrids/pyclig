# Examples

Six small command-line tools, each a uv workspace member that shows one pyclig feature. They are
ordered as a learning path: start at `01-hello` and work down.

## Run an example

Each example is one module, and its docstring lists the commands to try. Run them from the
example's own directory:

```bash
cd examples/01-hello
uv run hello --name Ada --shout
```

To install every example into the root environment instead, run `uv sync --all-packages` from
the repository root.

| Example | Script | Shows |
| --- | --- | --- |
| `01-hello` | `hello` | A single command, its help, version and run flags |
| `02-errors` | `pantry` | A group, its errors and exit codes |
| `03-output` | `fruit` | Human, plain and JSON output from one call, plus a test |
| `04-feedback` | `checkup` | Feedback on STDERR, logging and quiet mode |
| `05-prompts` | `depot` | Confirmations, secrets and the non-TTY refusal |
| `06-config` | `greeter` | Config files, profiles and precedence |

## PowerShell

The docstrings use Bash syntax. In PowerShell, swap these:

| Bash | PowerShell |
| --- | --- |
| `\| cat` | `\| Write-Output` |
| `2>/dev/null` | `2>$null` |
| `echo $?` | `$LASTEXITCODE` |
| `VAR=1 cmd` | `$env:VAR = "1"; cmd` |
| `</dev/null` | `$null \|` |

## Not covered here

The root `README.md` documents the features that have no example:

- `pyclig.run`
- `ctx.cleanup`
- `ctx.pager`
- `NoneOr`
- `options.output`, `options.port` and `options.timeout`
- `dotenv=True`
- `deprecated=`
- `prompt=` options
- `hanging`
