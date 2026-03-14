# Contributing to Ouro Loop

Thanks for your interest in contributing! This project is still in its early stages, so contributions are especially welcome.

## How to contribute

### Report bugs or suggest features

Open an issue. Include:
- What you expected to happen
- What actually happened
- Steps to reproduce (if applicable)
- Your project type (e.g., "blockchain L1", "consumer app")

### Submit a pull request

1. Fork the repo
2. Create a branch: `git checkout -b my-feature`
3. Make your changes
4. Test: run `python prepare.py scan` on a real project
5. Submit a PR with a clear description

### Add examples

We especially welcome real-world examples in `examples/`. If you've used Ouro Loop on a project and can share (sanitized) `CLAUDE.md`, `phase-plan.md` files, and examples of **Autonomous Discovery & Remediation Logs**, that's incredibly valuable.

### Improve modules

The methodology modules in `modules/` are the heart of the project. If you've discovered a pattern that consistently works across projects, propose it.

## Guidelines

- **Keep it simple.** This project follows Ouro Loop's philosophy: fewer files, less complexity. Resist the urge to add abstractions.
- **Real over theoretical.** Every module and template should come from real project experience, not hypothetical best practices.
- **Test on real projects.** Before submitting methodology changes, verify they work on at least one real codebase.

## Code style

- Python: follow PEP 8, no external dependencies unless absolutely necessary
- Markdown: keep it concise, use tables over prose where possible
- No emojis in code or documentation (except the watchdog overlay, which is part of the spec)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
