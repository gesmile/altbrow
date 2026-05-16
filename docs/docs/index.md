# Altbrow — Developer Documentation

Altbrow is a Python CLI tool for deep analysis of websites: semantic structure,
external dependencies, cookies, and structured data (JSON-LD, Microdata).

## Documentation

| Page | Content |
|------|---------|
| [Provider System](provider.md) | Provider schema, categories, tier, file formats, DNS resolve filter |
| [Exit Codes](exitcodes.md) | CLI exit codes with implementation status |
| [Configuration API](config.md) | Python API for config loading and validation (autodoc) |
| [API Reference](api.md) | All modules — functions, parameters, return types (autodoc) |

## Quick start

```bash
pip install -e .[dev]

altbrow --validate-config   # check config
altbrow --build-cache       # build provider cache
altbrow <URL>               # analyse a URL
```

See [README](../../README.md) for install instructions and usage examples.
