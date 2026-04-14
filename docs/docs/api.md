# API Help


```

usage: altbrow [-h] [-V] [--config CONFIG] [-o OUTPUT] [-f {text,yaml,json}] [-v] [--client-profile {passive,browser,consented}] [--validate-config] [--build-cache] [url]

positional arguments:
  url                   URL to analyze

options:
  -h, --help            show this help message and exit
  -V, --version         show program's version number and exit
  --config CONFIG       Path to configuration file (TOML)
  -o OUTPUT, --output OUTPUT
                        Write result to file
  -f {text,yaml,json}, --format {text,yaml,json}
                        Output format (default: text)
  -v, --verbose         Increase text detail level (-vv, -vvv)
  --client-profile {passive,browser,consented}
                        HTTP client behavior profile (default: from config)
  --validate-config     Validate altbrow.toml and exit
  --build-cache         (Re)build provider cache DB and exit

```