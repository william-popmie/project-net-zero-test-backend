"""
train.py — Minimal Linear Regression trained with Gradient Descent

No libraries. Trains a model: y = w*x + b to fit a straight line.
The "stupid" dataset: y = 3x + 2 with a bit of noise.

Run:  python train.py
Test: pytest test_train.py
"""

import random
import math


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def generate_data(n: int = 50, seed: int = 42) -> list[tuple[float, float]]:
    import random
    rng = random.Random(seed)
    uniform = rng.uniform
    inv_n = 1.0 / n if n else 1.0
    return [(i * inv_n, 3.0 * (i * inv_n) + 2.0 + uniform(-0.1, 0.1)) for i in range(n)]

def predict(x: float, w: float, b: float) -> float:
    return w * x + b

def mse_loss(data: list[tuple[float, float]], w: float, b: float) -> float:
    """Mean Squared Error loss."""
    total = 0.0
    for x, y in data:
        error = predict(x, w, b) - y
        total += error ** 2
    return total / len(data)

def compute_gradients(
    data: list[tuple[float, float]], w: float, b: float
) -> tuple[float, float]:
    """Compute dL/dw and dL/db via backprop (closed-form for MSE)."""
    n = len(data)
    dw = 0.0
    db = 0.0
    for x, y in data:
        error = predict(x, w, b) - y
        dw += (2 / n) * error * x
        db += (2 / n) * error
    return dw, db

def train(
    data: list[tuple[float, float]],
    lr: float = 0.5,
    epochs: int = 200,
    w_init: float = 0.0,
    b_init: float = 0.0,
) -> dict:
    """
    Gradient descent training loop.

    Returns:
        w, b      — learned parameters
        losses    — loss per epoch
        epochs    — number of epochs run
    """
    w, b = w_init, b_init
    losses = []

    for epoch in range(epochs):
        loss = mse_loss(data, w, b)
        losses.append(loss)

        dw, db = compute_gradients(data, w, b)
        w -= lr * dw
        b -= lr * db

        if (epoch + 1) % 50 == 0:
            print(f"  Epoch {epoch + 1:>4} | Loss: {loss:.6f} | w={w:.4f}, b={b:.4f}")

    return {"w": w, "b": b, "losses": losses, "epochs": epochs}

def evaluate(data: list[tuple[float, float]], w: float, b: float) -> dict:
    """Returns MSE and mean absolute error on the dataset."""
    mse = mse_loss(data, w, b)
    mae = sum(abs(predict(x, w, b) - y) for x, y in data) / len(data)
    return {"mse": mse, "mae": mae}
