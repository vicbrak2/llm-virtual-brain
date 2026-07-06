# Contributing to LLM Virtual Brain

Thank you for your interest in contributing! This document outlines the process and guidelines.

## Code of Conduct

- Be respectful and inclusive
- No harassment or discrimination
- Focus on constructive feedback

## Getting Started

1. **Fork** the repository
2. **Clone** your fork locally
3. **Create a branch** for your feature: `git checkout -b feature/my-feature`
4. **Install dev dependencies**: `pip install -e ".[dev]"`
5. **Make changes** and test
6. **Commit** with clear messages
7. **Push** to your fork and open a **Pull Request**

## Development Setup

```bash
# Clone
git clone https://github.com/vicbrak2/llm-virtual-brain.git
cd llm-virtual-brain

# Virtual env
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with dev deps
pip install -e ".[dev]"
```

## Code Style

We use `black` and `isort`:

```bash
# Format
black brain/
isort brain/

# Check
black --check brain/
isort --check brain/
```

## Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=brain

# Type check
mypy brain/
```

## PR Guidelines

1. **Title**: "Add [feature]" or "Fix [bug]" (clear and descriptive)
2. **Description**: What and why (not just what)
3. **Tests**: Add tests for new features
4. **Docs**: Update README or docs if needed
5. **No breaking changes** (unless major version bump)

## Commit Messages

```
# Good
feat: add password vault context provider
fix: handle empty LLM responses gracefully

# Bad
fix stuff
asdf
```

## Issues

- **Bugs**: Include steps to reproduce and version
- **Features**: Explain use case and expected behavior
- **Questions**: Use discussions if unsure

## Release Process

(For maintainers)

```bash
# Bump version in setup.py + pyproject.toml
# Create git tag
git tag v1.0.1
git push origin v1.0.1

# Build and publish to PyPI
python -m build
twine upload dist/*
```

## Questions?

- Open an [issue](https://github.com/vicbrak2/llm-virtual-brain/issues)
- Check [Discussions](https://github.com/vicbrak2/llm-virtual-brain/discussions)

Thank you! 🙏
