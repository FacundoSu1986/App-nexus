# Contributing Guide

Thank you for your interest in contributing to **App-nexus**! This guide will help you get started.

## How to Contribute

1. Fork the repository.
2. Create a branch for your change: `git checkout -b my-change`.
3. Make your changes and ensure the tests pass.
4. Commit with a descriptive message: `git commit -m "Description of change"`.
5. Push your branch: `git push origin my-change`.
6. Open a Pull Request describing your changes.

## Environment Setup

```bash
# Clone your fork
git clone https://github.com/<your-username>/App-nexus.git
cd App-nexus

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v
```

## Code Style

- We follow **PEP 8** conventions for Python.
- Use type hints whenever possible.
- Docstrings should follow the NumPy/Google format.
- The user interface should be in **English**.

## Interface Language

All user-visible text strings should be in **English**. This includes:

- Button and field labels
- Dialog messages (warnings, errors, information)
- Status bar messages
- Column headings and tabs
- Analysis report text

Code comments and log messages may remain in either English or Spanish.

## Tests

- Tests are written with **pytest**.
- Place tests in the `tests/` folder with the `test_` prefix.
- Run tests before submitting your PR:

```bash
python -m pytest tests/ -v
```

## Reporting Bugs

If you find a bug, open an issue including:

- Description of the problem
- Steps to reproduce it
- Expected vs. actual behaviour
- Python version and operating system

## Suggestions and Improvements

Suggestions are welcome. Open an issue with the `enhancement` label to propose new features.
