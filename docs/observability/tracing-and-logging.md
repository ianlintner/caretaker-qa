# Tracing & Logging

The server uses the [`tracing`](https://docs.rs/tracing) crate for both structured logging and distributed tracing, with [`tracing-subscriber`](https://docs.rs/tracing-subscriber) for output formatting.

## Structured Logging

### Log format

Logs can be emitted in structured JSON format (recommended for production) or pretty-printed for development.

| Variable            | Type   | Default | Description                  |
| ------------------- | ------ | ------- | ---------------------------- |
| `RUST_LOG`          | String | `info`  | Log level filter             |
| `OAUTH2_LOG_FORMAT` | String | `json`  | Log format (`json`/`pretty`) |

### Filtering

Use `RUST_LOG` to control verbosity:

- Minimal: `RUST_LOG=info`
- Debug for this crate: `RUST_LOG=rust_oauth2_server=debug,info`
- Suppress noisy dependencies: `RUST_LOG=info,sqlx=warn,actix_web=warn`

### Correlation

Where applicable, logs include correlation IDs and request context. Combine logs with traces for full request-to-database visibility.

## Distributed Tracing

The server supports distributed tracing via OpenTelemetry.

### What's instrumented

- Incoming HTTP requests (middleware)
- Core handler/actor operations
- Eventing publishes (best-effort) carry W3C trace context in the event envelope

### OTLP export

| Variable                      | Type    | Default                 | Description                          |
| ----------------------------- | ------- | ----------------------- | ------------------------------------ |
| `OAUTH2_OTLP_ENDPOINT`        | String  | `http://localhost:4317` | OTLP gRPC endpoint                   |
| `OAUTH2_OTLP_PROTOCOL`        | String  | `grpc`                  | Protocol (`grpc` or `http/protobuf`) |
| `OAUTH2_OTLP_TRACES_ENABLED`  | Boolean | `true`                  | Enable trace export                  |
| `OAUTH2_OTLP_METRICS_ENABLED` | Boolean | `true`                  | Enable metrics export                |

A common local setup is Jaeger all-in-one:

```bash
docker run -d --name jaeger \
  -p 4317:4317 \
  -p 16686:16686 \
  jaegertracing/all-in-one:latest
```

Then visit Jaeger UI at `http://localhost:16686`.

### Context propagation

Incoming requests that include W3C headers:

- `traceparent`
- `tracestate`

will have that context propagated into server spans and (when events are emitted) into `EventEnvelope` fields.

See [Eventing](../eventing.md) for the envelope structure.
