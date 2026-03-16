"""Shell completion script generator."""
import sys


def register(subparsers):
    parser = subparsers.add_parser(
        'completion',
        help='Generate shell completion scripts'
    )
    parser.set_defaults(func=run_completion)
    parser.add_argument('shell', choices=['bash', 'zsh', 'fish'], help='Shell type')


def run_completion(args):
    """Generate and print shell completion script."""
    generators = {
        'bash': _bash_completion,
        'zsh': _zsh_completion,
        'fish': _fish_completion,
    }
    print(generators[args.shell]())


def _get_commands():
    """Get all available commands."""
    return [
        'init', 'auth', 'auth-export', 'auth-import', 'status',
        'listings', 'listing', 'reservations', 'reservation',
        'guests', 'owners', 'calendar', 'tasks', 'reviews', 'webhooks',
        'financials', 'occupancy', 'integrations', 'users', 'sync', 'search',
        'export', 'statements', 'views', 'schema', 'completion', 'exit-codes', 'agent',
    ]


def _get_global_flags():
    """Get global flags."""
    return [
        '--help', '--version', '--json', '--plain', '--tsv', '--no-color',
        '--select', '--results-only', '--dry-run', '--force',
        '--access-token', '--no-input', '--non-interactive',
    ]


def _bash_completion():
    commands = ' '.join(_get_commands())
    flags = ' '.join(_get_global_flags())
    return f'''# guesty-cli bash completion
# Add to ~/.bashrc: eval "$(guesty completion bash)"

_guesty_completions() {{
    local cur prev commands global_flags
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    commands="{commands}"
    global_flags="{flags}"

    # Subcommand-specific completions
    case "${{prev}}" in
        listings|listing)
            COMPREPLY=( $(compgen -W "list show update descriptions amenities --active --city --status --json --csv --live" -- "${{cur}}") )
            return 0
            ;;
        reservations|reservation)
            COMPREPLY=( $(compgen -W "list get create update cancel approve decline --status --from --to --source --listing --json --csv --live" -- "${{cur}}") )
            return 0
            ;;
        guests)
            COMPREPLY=( $(compgen -W "list get --json --csv" -- "${{cur}}") )
            return 0
            ;;
        owners)
            COMPREPLY=( $(compgen -W "list get revenue --json --csv" -- "${{cur}}") )
            return 0
            ;;
        tasks)
            COMPREPLY=( $(compgen -W "list get create update --status --listing --json --csv" -- "${{cur}}") )
            return 0
            ;;
        reviews)
            COMPREPLY=( $(compgen -W "list get --listing --json --csv" -- "${{cur}}") )
            return 0
            ;;
        webhooks)
            COMPREPLY=( $(compgen -W "list create delete test events --json" -- "${{cur}}") )
            return 0
            ;;
        sync)
            COMPREPLY=( $(compgen -W "listings reservations guests owners reviews tasks financials webhooks --full --incremental --dry-run --status --history" -- "${{cur}}") )
            return 0
            ;;
        completion)
            COMPREPLY=( $(compgen -W "bash zsh fish" -- "${{cur}}") )
            return 0
            ;;
        auth)
            COMPREPLY=( $(compgen -W "--refresh --revoke" -- "${{cur}}") )
            return 0
            ;;
    esac

    # Top-level completions
    if [[ ${{COMP_CWORD}} -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "${{commands}} ${{global_flags}}" -- "${{cur}}") )
        return 0
    fi

    # Flag completions
    if [[ "${{cur}}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${{global_flags}}" -- "${{cur}}") )
        return 0
    fi
}}

complete -F _guesty_completions guesty
'''


def _zsh_completion():
    commands = _get_commands()
    cmd_lines = '\n        '.join([f'"{cmd}:{cmd} management"' for cmd in commands])
    return f'''#compdef guesty
# guesty-cli zsh completion
# Add to ~/.zshrc: eval "$(guesty completion zsh)"

_guesty() {{
    local -a commands
    commands=(
        {cmd_lines}
    )

    _arguments -C \\
        '--help[Show help]' \\
        '--version[Show version]' \\
        '--json[Output as JSON]' \\
        '--plain[Output stable TSV]' \\
        '--no-color[Disable colors]' \\
        '--select[Select fields for JSON output]:fields:' \\
        '--results-only[Emit only primary results]' \\
        '--dry-run[Preview changes]' \\
        '--force[Skip confirmations]' \\
        '--access-token[Use provided access token directly]:token:' \\
        '--no-input[Never prompt; fail instead (for CI/agents)]' \\
        '1:command:->cmds' \\
        '*::arg:->args'

    case "$state" in
        cmds)
            _describe -t commands 'guesty commands' commands
            ;;
        args)
            case $words[1] in
                listings)
                    _arguments '1:action:(list show update descriptions amenities)' '--active[Active only]' '--city[Filter by city]:city:' '--json[JSON output]'
                    ;;
                reservations)
                    _arguments '1:action:(list get create cancel approve decline)' '--status[Filter status]:status:(confirmed canceled inquiry)' '--from[From date]:date:' '--to[To date]:date:'
                    ;;
                sync)
                    _arguments '1:endpoint:(listings reservations guests owners reviews tasks financials webhooks)' '--full[Full sync]' '--incremental[Incremental sync]' '--dry-run[Dry run]'
                    ;;
                completion)
                    _arguments '1:shell:(bash zsh fish)'
                    ;;
            esac
            ;;
    esac
}}

_guesty
'''


def _fish_completion():
    lines = ['# guesty-cli fish completion',
             '# Add to config: guesty completion fish | source', '']

    for cmd in _get_commands():
        lines.append(f'complete -c guesty -n "__fish_use_subcommand" -a "{cmd}" -d "{cmd} management"')

    # Global flags
    for flag in _get_global_flags():
        name = flag.lstrip('-')
        lines.append(f'complete -c guesty -l "{name}" -d "{name}"')

    # Subcommand completions
    lines.extend([
        '',
        '# listings subcommands',
        'complete -c guesty -n "__fish_seen_subcommand_from listings" -a "list show update descriptions amenities"',
        'complete -c guesty -n "__fish_seen_subcommand_from reservations" -a "list get create cancel approve decline"',
        'complete -c guesty -n "__fish_seen_subcommand_from sync" -a "listings reservations guests owners reviews tasks financials webhooks"',
        'complete -c guesty -n "__fish_seen_subcommand_from completion" -a "bash zsh fish"',
    ])

    return '\n'.join(lines)
