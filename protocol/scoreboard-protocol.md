# Scoreboard Protocol

Pybricks broadcast channel:

```python
CHANNEL = 1
```

## Message values

Use one integer so it stays small and reliable.

```text
-1              blank display
0..999          show number
10000..19999    FULL PULL scroll, offset = value - 10000
```

## Why one integer?

Pybricks broadcast packets are small. One integer is easy to send, easy to receive, and enough for scoreboard state.

## Example

Master:

```python
hub = PrimeHub(broadcast_channel=1)
hub.ble.broadcast(42)
```

Display hub:

```python
hub = PrimeHub(observe_channels=[1])
message = hub.ble.observe(1)
```

