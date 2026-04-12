# Altbrow

An alternative, crawler-like browser that looks beneath the surface of the semantic web.   
Add IP or domain lists to classify all connected domains.   
This project is still in a very early alpha stage.



## Usage

```

.venv\Scripts\activate
pip install -e .

altbrow --help
altbrow --validate-config
altbrow --build-cache
altbrow URL

```



### Output

```

altbrow https://tmp.gedankenfalle.de/html5

=== Summary ===
External domains : 25 (ads: 4, infrastructure: 9, local: 1, telemetry: 2, unknown: 9)
External IPs     : 0
Cookies          : 0
JSON-LD blocks   : 0
Microdata blocks : 2

```