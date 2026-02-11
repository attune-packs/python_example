# Python Example Pack for Attune

A complete example pack demonstrating Python actions, a stateful counter sensor with keystore integration, and HTTP requests using the `requests` library.

## Purpose

This pack exercises as many parts of the Attune SDLC as possible:

- **Python actions** with the wrapper-based execution model
- **Python sensor** with RabbitMQ rule lifecycle integration
- **Trigger types** with structured payload schemas
- **Rules** connecting triggers to actions with parameter mapping
- **Keystore integration** for persistent sensor state across restarts
- **External Python dependencies** (`requests`, `pika`)
- **Per-rule scoped state** — each rule subscription gets its own counter

## Components

### Actions

| Ref | Description |
|-----|-------------|
| `python_example.hello` | Returns `"Hello, Python"` — minimal action |
| `python_example.http_example` | Uses `requests` to GET `https://example.com` |
| `python_example.read_counter` | Consumes a counter value and returns a formatted message |

### Triggers

| Ref | Description |
|-----|-------------|
| `python_example.counter` | Fires periodically with an incrementing counter per rule |

### Sensors

| Ref | Description |
|-----|-------------|
| `python_example.counter_sensor` | Manages per-rule counters stored in the Attune keystore |

### Rules

| Ref | Description |
|-----|-------------|
| `python_example.count_and_log` | Wires the counter trigger to the `read_counter` action |

## Installation

### As a Git Pack (recommended)

```bash
# Install via the Attune CLI from a git repository
attune pack install https://github.com/attune-automation/pack-python-example.git

# Or via the API
curl -X POST "http://localhost:8080/api/v1/packs/install" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"source": "git", "url": "https://github.com/attune-automation/pack-python-example.git"}'
```

### Local Development (submodule)

If you're developing against the Attune repository:

```bash
cd attune

# Add as a git submodule in packs.examples/
git submodule add <your-repo-url> packs.examples/python_example

# Or if you already have the directory, initialize it:
cd packs.examples/python_example
git init
git remote add origin <your-repo-url>
```

### Manual / Volume Mount

Copy or symlink the pack into your Attune packs directory:

```bash
cp -r python_example /opt/attune/packs/python_example
# Then restart services to pick it up, or use the dev packs volume
```

## Dependencies

Declared in `requirements.txt`:

- `requests>=2.28.0` — HTTP client for the `http_example` action and sensor API calls
- `pika>=1.3.0` — RabbitMQ client for the counter sensor

These are installed automatically when the pack is loaded by a Python worker with dependency management enabled.

## How It Works

### Counter Sensor Flow

```
┌──────────────────────────────────────────────────────────┐
│                   counter_sensor.py                      │
│                                                          │
│  1. Startup: fetch active rules from GET /api/v1/rules   │
│  2. Listen: RabbitMQ queue sensor.python_example.*       │
│     for rule.created / rule.enabled / rule.disabled /    │
│     rule.deleted messages                                │
│  3. Per active rule, spawn a timer thread:               │
│                                                          │
│     ┌────────────────────────────────────────┐           │
│     │  Timer Thread (1 tick/sec per rule)     │           │
│     │                                        │           │
│     │  GET /api/v1/keys/{key} → read counter │           │
│     │  counter += 1                          │           │
│     │  PUT /api/v1/keys/{key} → write back   │           │
│     │  POST /api/v1/events → emit event      │           │
│     └────────────────────────────────────────┘           │
│                                                          │
│  4. On shutdown: stop all timer threads gracefully       │
└──────────────────────────────────────────────────────────┘
```

### Keystore Key Naming

Each rule gets its own counter key:

```
python_example.counter.<rule_ref_with_dots_replaced_by_underscores>
```

For example, a rule with ref `python_example.count_and_log` stores its counter at:

```
python_example.counter.python_example_count_and_log
```

### Event Payload

Each emitted event has this structure:

```json
{
  "counter": 42,
  "rule_ref": "python_example.count_and_log",
  "sensor_ref": "python_example.counter_sensor",
  "fired_at": "2025-01-15T12:00:00.000000+00:00"
}
```

### Rule Parameter Mapping

The included `count_and_log` rule maps trigger payload fields to action parameters:

```yaml
action_params:
  counter: "{{ trigger.payload.counter }}"
  rule_ref: "{{ trigger.payload.rule_ref }}"
```

The `read_counter` action then returns:

```json
{
  "message": "Counter value is 42 (from rule: python_example.count_and_log)",
  "counter": 42,
  "rule_ref": "python_example.count_and_log"
}
```

## Testing Individual Components

### Test the hello action

```bash
attune action execute python_example.hello
# Output: {"message": "Hello, Python"}
```

### Test the HTTP action

```bash
attune action execute python_example.http_example
# Output: {"status_code": 200, "url": "https://example.com", ...}
```

### Test the read_counter action directly

```bash
attune action execute python_example.read_counter --param counter=99 --param rule_ref=test
# Output: {"message": "Counter value is 99 (from rule: test)", ...}
```

### Enable the rule to start the counter sensor loop

```bash
# The rule is enabled by default when the pack is loaded.
# To manually enable/disable:
attune rule enable python_example.count_and_log
attune rule disable python_example.count_and_log

# Monitor executions produced by the rule:
attune execution list --action python_example.read_counter
```

## Configuration

The pack supports the following configuration in `pack.yaml`:

| Setting | Default | Description |
|---------|---------|-------------|
| `counter_key_prefix` | `python_example.counter` | Prefix for keystore keys |

The sensor supports these parameters:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `default_interval_seconds` | `1` | Default tick interval per rule |
| `key_prefix` | `python_example.counter` | Keystore key prefix |

The trigger supports per-rule configuration:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `interval_seconds` | `1` | Seconds between counter ticks |

## Development

```bash
# Run the sensor manually for testing
export ATTUNE_API_URL=http://localhost:8080
export ATTUNE_API_TOKEN=<your-token>
export ATTUNE_MQ_URL=amqp://guest:guest@localhost:5672/
python3 sensors/counter_sensor.py

# Run an action manually
echo '{"parameters": {"name": "World"}}' | python3 actions/hello.py
```

## License

MIT